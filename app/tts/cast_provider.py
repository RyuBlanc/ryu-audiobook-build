from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.chapters.characters import infer_speaker_for_quote, _all_dialogue_spans
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
    ):
        self.narrator_provider = narrator_provider
        self.narrator_voice = narrator_voice
        self.profiles = {k.casefold(): v for k, v in profiles.items()}
        self.assignments = {k.casefold(): v for k, v in assignments.items() if v}
        self.narrating_character = (narrating_character or "").casefold()
        self.backend_override = backend_override or "automatic"
        self._providers: dict[str, tuple[TTSProvider, str]] = {}

    @property
    def recommended_chunk_chars(self) -> int:
        limits = [300 if profile.provider == "chatterbox" else 1400 for profile in self.profiles.values()]
        return min(limits) if limits else getattr(self.narrator_provider, "recommended_chunk_chars", 1400)

    @property
    def recommended_chunk_sentences(self) -> int:
        if any(profile.provider == "chatterbox" for profile in self.profiles.values()):
            return 1
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

    def generation_signature(self) -> str:
        payload = {
            "narrator": self.narrator_voice,
            "assignments": sorted(self.assignments.items()),
            "profiles": sorted(
                (k, self.profiles[k].provider, self.profiles[k].voice_id, self.profiles[k].sample_path)
                for k in self.assignments if k in self.profiles
            ),
            "narrating_character": self.narrating_character,
            "backend_override": self.backend_override,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def _speaker_for(self, text: str, start: int, end: int, last_speaker: str | None) -> str | None:
        return infer_speaker_for_quote(
            text,
            start,
            end,
            list(self.assignments.keys()),
            narrator_name=self.narrating_character or None,
            last_speaker=last_speaker,
        )

    def split_for_cast(self, text: str, fallback_voice: str | None):
        # Use the same dialogue span detector as Voice Cast analysis so
        # generation and review cannot disagree about what counts as dialogue.
        spans = _all_dialogue_spans(text)

        if not spans:
            return [(text, fallback_voice)]

        parts = []
        cursor = 0
        last_speaker = None
        for start, end, _dialogue in spans:
            if start > cursor:
                parts.append((text[cursor:start], fallback_voice))

            speaker = self._speaker_for(text, start, end, last_speaker)
            voice = self.assignments.get(speaker.casefold()) if speaker else fallback_voice
            if speaker:
                last_speaker = speaker.casefold()

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
            cached = (provider, provider_voice)
            self._providers[profile_name] = cached
        provider, provider_voice = cached
        return provider.synthesize(text, output_path, provider_voice)
