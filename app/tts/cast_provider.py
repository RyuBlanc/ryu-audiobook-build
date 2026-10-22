from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from pathlib import Path

from app.chapters.characters import infer_speaker_for_quote, _all_dialogue_spans
from app.chapters.assignment_utils import assignment_speakers
from app.tts.base import TTSProvider
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import VoiceProfile

QUOTE_PATTERNS = (
    re.compile(r'“([^”]+)”'),
    re.compile(r'「([^」]+)」'),
    re.compile(r'『([^』]+)』'),
    re.compile(r'"([^"]+)"'),
)


class CastAwareProvider(TTSProvider):
    """Route attributed dialogue to saved cast voices while narration uses the fallback voice."""

    def __init__(
        self,
        narrator_provider: TTSProvider,
        narrator_voice: str | None,
        profiles: dict[str, VoiceProfile],
        assignments: dict[str, str],
        narrating_character: str | None = None,
        backend_override: str = "automatic",
        narrator_profile: VoiceProfile | None = None,
    ):
        self.narrator_provider = narrator_provider
        self.narrator_voice = narrator_voice
        self.narrator_profile = narrator_profile
        self.profiles = {k.casefold(): v for k, v in profiles.items()}
        self.assignments = {k.casefold(): v for k, v in assignments.items() if v}
        self.narrating_character = (narrating_character or "").casefold()
        self.backend_override = backend_override or "automatic"
        self._providers: dict[str, tuple[TTSProvider, str]] = {}
        self._status_callback = None

    @property
    def recommended_chunk_chars(self) -> int:
        limits = []
        for profile in self.profiles.values():
            if profile.provider == "chatterbox":
                limits.append(300)
            elif profile.provider == "qwen-character":
                limits.append(1800)
            else:
                limits.append(getattr(self.narrator_provider, "recommended_chunk_chars", 1400))
        if not limits:
            return getattr(self.narrator_provider, "recommended_chunk_chars", 1400)
        return min(limits)

    @property
    def recommended_chunk_sentences(self) -> int:
        if any(profile.provider == "chatterbox" for profile in self.profiles.values()):
            return 1
        if any(profile.provider == "qwen-character" for profile in self.profiles.values()):
            return 8
        return getattr(self.narrator_provider, "recommended_chunk_sentences", 2)

    @property
    def stop_on_failure(self) -> bool:
        if getattr(self.narrator_provider, "stop_on_failure", False):
            return True
        # A character voice provider failing mid-book should stop the run
        # cleanly rather than burning time failing the same voice on every
        # later chapter. Completed chunks remain resumable.
        for profile in self.profiles.values():
            if profile.provider in {"edge-tts", "chatterbox"}:
                if profile.name.casefold() in self.assignments or any(
                    value.casefold() == profile.name.casefold()
                    for value in self.assignments.values()
                ):
                    return True
        return False

    def voices(self) -> list[str]:
        return [self.narrator_voice] if self.narrator_voice else []

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback
        narrator_callback = getattr(self.narrator_provider, "set_status_callback", None)
        if callable(narrator_callback):
            narrator_callback(callback)
        for provider, _voice in self._providers.values():
            child_callback = getattr(provider, "set_status_callback", None)
            if callable(child_callback):
                child_callback(callback)


    def request_cancel(self) -> None:
        """Forward non-blocking cancellation to the active narrator and cast voices."""
        providers = [self.narrator_provider, *[item[0] for item in self._providers.values()]]
        seen = set()
        for provider in providers:
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            cancel = getattr(provider, "request_cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    pass

    @staticmethod
    def _profile_signature(profile: VoiceProfile | None) -> dict | None:
        if profile is None:
            return None
        data = {
            "name": profile.name,
            "provider": profile.provider,
            "voice_id": profile.voice_id,
            "sample_path": profile.sample_path,
            "model_id": profile.model_id,
            "backend": profile.backend,
            "language": profile.language,
            "notes": profile.notes,
            "authorized": profile.authorized,
            "exaggeration": profile.exaggeration,
            "cfg_weight": profile.cfg_weight,
            "style_preset": profile.style_preset,
            "qwen_mode": profile.qwen_mode,
            "qwen_prompt": profile.qwen_prompt,
            "qwen_seed": profile.qwen_seed,
            "reference_text": profile.reference_text,
            "qwen_anchor_path": profile.qwen_anchor_path,
            "qwen_anchor_text": profile.qwen_anchor_text,
            "qwen_profile_id": profile.qwen_profile_id,
        }
        # A reference can be replaced in-place while its path stays the same.
        # Include content digests so resumed chunks cannot silently keep audio
        # rendered with the previous reference recording.
        for key, raw_path in (("sample_audio_sha256", profile.sample_path),
                              ("anchor_audio_sha256", profile.qwen_anchor_path)):
            digest = None
            if raw_path:
                path = Path(raw_path).expanduser()
                if path.is_file():
                    hasher = hashlib.sha256()
                    try:
                        with path.open("rb") as handle:
                            for block in iter(lambda: handle.read(1024 * 1024), b""):
                                hasher.update(block)
                        digest = hasher.hexdigest()
                    except OSError:
                        digest = "unreadable"
                else:
                    digest = "missing"
            data[key] = digest
        return data

    def generation_signature(self) -> str:
        narrator_provider_signature = getattr(self.narrator_provider, "generation_signature", None)
        if callable(narrator_provider_signature):
            narrator_engine = narrator_provider_signature()
        else:
            narrator_engine = {
                "class": f"{self.narrator_provider.__class__.__module__}.{self.narrator_provider.__class__.__qualname__}",
                "voice": self.narrator_voice,
            }
        payload = {
            "narrator": self.narrator_voice,
            "narrator_profile": self._profile_signature(self.narrator_profile),
            "narrator_engine": narrator_engine,
            "assignments": sorted(self.assignments.items()),
            "profiles": sorted(
                (
                    self._profile_signature(self.profiles.get(name.casefold()))
                    for name in set(self.assignments.values())
                ),
                key=lambda item: str((item or {}).get("name", "")).casefold(),
            ),
            "narrating_character": self.narrating_character,
            "backend_override": self.backend_override,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _assignment_for_span(self, text: str, start: int, end: int, dialogue_assignments) -> dict | None:
        assignments = list(dialogue_assignments or [])
        if not assignments:
            return None

        # Generation text may change length during typography cleanup or
        # pronunciation substitution. Overlap alone is not evidence that a
        # saved speaker belongs to this quote: it can silently assign a nearby
        # line to the wrong character. Accept an exact source span, or a
        # normalized exact-text match (with offsets only breaking duplicate
        # quote ties).
        candidates = []
        raw = text[start:end].strip()
        normalized_raw = re.sub(r"[^\w]+", " ", raw, flags=re.UNICODE).casefold().strip()

        for item in assignments:
            speakers = assignment_speakers(item)
            if not speakers:
                continue
            try:
                a_start = int(item.get("start", -1))
                a_end = int(item.get("end", -1))
            except (TypeError, ValueError):
                a_start, a_end = -1, -1

            item_text = str(item.get("text") or "").strip()
            normalized_item = re.sub(r"[^\w]+", " ", item_text, flags=re.UNICODE).casefold().strip()
            if a_start == start and a_end == end:
                score = 200000.0
            elif normalized_item and normalized_item == normalized_raw:
                score = 100000.0 - (abs(start - a_start) * 0.01 if a_start >= 0 else 0.0)
            else:
                continue
            candidates.append((score, item))

        if not candidates:
            return None
        _score, item = max(candidates, key=lambda value: value[0])
        return item

    def _speakers_for(
        self,
        text: str,
        start: int,
        end: int,
        last_speaker: str | None,
        dialogue_assignments=None,
    ) -> tuple[list[str], str | None]:
        manual = self._assignment_for_span(text, start, end, dialogue_assignments)
        if manual:
            speakers = assignment_speakers(manual)
            if speakers:
                return speakers, (str(manual.get("multi_speaker_mode") or "chorus").strip().lower())

        speaker = self._speaker_for(text, start, end, last_speaker)
        return ([speaker] if speaker else []), None

    def _speaker_for(self, text: str, start: int, end: int, last_speaker: str | None) -> str | None:
        return infer_speaker_for_quote(
            text,
            start,
            end,
            list(self.assignments.keys()),
            narrator_name=self.narrating_character or None,
            last_speaker=last_speaker,
        )

    def split_for_cast(self, text: str, fallback_voice: str | None, dialogue_assignments=None):        # Use the same dialogue span detector as Voice Cast analysis so
        # generation and review cannot disagree about what counts as dialogue.
        spans = _all_dialogue_spans(text)

        if not spans:
            return [(text, fallback_voice)]

        parts = []
        cursor = 0
        last_speaker = None
        alternating_voice_index = 0
        for start, end, _dialogue in spans:
            if start > cursor:
                parts.append((text[cursor:start], fallback_voice))

            speakers, multi_mode = self._speakers_for(
                text,
                start,
                end,
                last_speaker,
                dialogue_assignments=dialogue_assignments,
            )
            assigned_voices = [
                self.assignments.get(speaker.casefold())
                for speaker in speakers
                if self.assignments.get(speaker.casefold())
            ]
            if assigned_voices:
                if len(assigned_voices) > 1 and multi_mode == "alternating":
                    # Alternate one configured voice per dialogue span; do not
                    # duplicate the same line or send an unsupported voice list.
                    voice = assigned_voices[alternating_voice_index % len(assigned_voices)]
                    alternating_voice_index += 1
                elif len(assigned_voices) > 1 and multi_mode != "sequential":
                    voice = assigned_voices
                else:
                    voice = assigned_voices[0]
            else:
                voice = fallback_voice
            if speakers:
                last_speaker = speakers[-1].casefold()

            raw = text[start:end].strip()
            dialogue = raw

            # Normalize only the dialogue marker for synthesis. The source
            # text stays untouched in narration.json and the project.
            if len(dialogue) >= 2 and dialogue[0] in '“"「『' and dialogue[-1] in '”"」』':
                dialogue = dialogue[1:-1].strip()
            else:
                stripped = dialogue.lstrip(" \t")
                if stripped and stripped[0] in "—–-":
                    dialogue = stripped[1:].strip()

            if dialogue:
                if (
                    assigned_voices
                    and len(assigned_voices) > 1
                    and multi_mode == "sequential"
                ):
                    for assigned_voice in assigned_voices:
                        parts.append((dialogue, assigned_voice))
                else:
                    parts.append((dialogue, voice))
            cursor = end

        if cursor < len(text):
            parts.append((text[cursor:], fallback_voice))
        return [(t, v) for t, v in parts if t.strip()]

    def close(self) -> None:
        providers = [self.narrator_provider, *[item[0] for item in self._providers.values()]]
        seen = set()
        for provider in providers:
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            close = getattr(provider, "close", None)
            if callable(close):
                close()

    def _provider_cache_key(self, profile_name: str, profile: VoiceProfile) -> str:
        backend = self.backend_override if self.backend_override != "automatic" else (profile.backend or "automatic")
        if profile.provider == "qwen-character" and str(profile.qwen_mode or "custom").casefold() in {"custom", "clone"}:
            return "shared:qwen:" + json.dumps([backend, profile.model_id or "auto", profile.qwen_mode or "custom"], separators=(",", ":"))
        if profile.provider == "chatterbox":
            return "shared:chatterbox:" + json.dumps([backend, profile.language or "en", profile.model_id == "chatterbox-multilingual"], separators=(",", ":"))
        return profile_name

    @staticmethod
    def _configure_profile_request(provider: TTSProvider, profile: VoiceProfile) -> None:
        if profile.provider == "qwen-character":
            provider.voice_id = profile.voice_id
            provider.language = profile.language or "English"
            provider.instruct = profile.qwen_prompt or profile.notes
            provider.qwen_seed = profile.qwen_seed
            provider.reference_audio = Path(profile.sample_path).expanduser() if profile.sample_path else None
            provider.reference_text = profile.reference_text or ""
            provider.qwen_anchor_path = Path(profile.qwen_anchor_path).expanduser() if profile.qwen_anchor_path else None
            provider.qwen_anchor_text = profile.qwen_anchor_text or ""
            provider.qwen_profile_id = profile.qwen_profile_id or ""
        elif profile.provider == "chatterbox":
            reference = Path(profile.sample_path).expanduser() if profile.sample_path else None
            if reference is None or not reference.is_file():
                raise RuntimeError(f"Custom voice profile '{profile.name}' has no valid reference audio.")
            provider.reference_audio = reference.resolve()
            provider.exaggeration = profile.exaggeration
            provider.cfg_weight = profile.cfg_weight

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        profile_name = voice.casefold() if voice else ""
        profile = self.profiles.get(profile_name)
        if profile is None:
            return self.narrator_provider.synthesize(text, output_path, self.narrator_voice)
        cached = self._providers.get(profile_name)
        if cached is None:
            cached = provider_from_profile(profile)
            provider, provider_voice = cached
            if self.backend_override != "automatic" and hasattr(provider, "backend"):
                provider.backend = self.backend_override
            child_callback = getattr(provider, "set_status_callback", None)
            if callable(child_callback):
                child_callback(self._status_callback)
            cached = (provider, provider_voice)
            self._providers[profile_name] = cached
        provider, provider_voice = cached
        return provider.synthesize(text, output_path, provider_voice)
