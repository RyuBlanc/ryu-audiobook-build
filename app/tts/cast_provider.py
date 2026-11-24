from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from app.chapters.characters import infer_speaker_for_quote, _all_dialogue_spans
from app.chapters.assignment_utils import assignment_speakers
from app.core.character_identity import character_identity_key, parse_character_identity_key
from app.tts.base import TTSProvider
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import VoiceProfile
from app.tts.providers.qwen_character import QwenCharacterProvider
from app.tts.expression import EXPRESSION_PIPELINE_VERSION
from app.tts.qwen_model_preference import get_qwen_model_preference

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
        identity_assignments: dict[str, str] | None = None,
        unassigned_voice: str | None = None,
    ):
        self.narrator_provider = narrator_provider
        self.narrator_voice = narrator_voice
        self.narrator_profile = narrator_profile
        self.profiles = {k.casefold(): v for k, v in profiles.items()}
        self.assignments = {k.casefold(): v for k, v in assignments.items() if v}
        # Keep scoped keys even when a character is intentionally unassigned.
        # An empty identity must not fall through to another series' name map.
        self.identity_assignments = {
            str(k).casefold(): str(v or "").strip()
            for k, v in (identity_assignments or {}).items()
            if parse_character_identity_key(str(k)) is not None
        }
        self._identity_series_by_name: dict[str, set[str]] = {}
        for key in self.identity_assignments:
            parsed = parse_character_identity_key(key)
            if parsed:
                series, name = parsed
                self._identity_series_by_name.setdefault(name, set()).add(series)
        self.narrating_character = (narrating_character or "").casefold()
        self.unassigned_voice = str(unassigned_voice or "").strip()
        self.backend_override = backend_override or "automatic"
        self._providers: dict[str, tuple[TTSProvider, str]] = {}
        self._status_callback = None
        self._generation_context: dict[str, str] = {"before": "", "after": ""}
        self._batch_contexts: list[dict[str, str]] = []

    @property
    def recommended_chunk_chars(self) -> int:
        limits = []
        for profile in self.profiles.values():
            if profile.provider == "chatterbox":
                limits.append(300)
            elif profile.provider == "qwen-character":
                limits.append(QwenCharacterProvider.recommended_chunk_chars)
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
            return QwenCharacterProvider.recommended_chunk_sentences
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
                    for value in [*self.assignments.values(), *self.identity_assignments.values()]
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
        if str(profile.provider or "").casefold() == "qwen-character":
            # Context-aware delivery/sampling now affects CustomVoice, VoiceDesign,
            # and Clone. Invalidate every Qwen mode when its synthesis policy changes.
            data["expression_pipeline_version"] = EXPRESSION_PIPELINE_VERSION
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
            "qwen_global_model_preference": get_qwen_model_preference(),
            "narrator": self.narrator_voice,
            "narrator_profile": self._profile_signature(self.narrator_profile),
            "narrator_engine": narrator_engine,
            "assignments": sorted(self.assignments.items()),
            "identity_assignments": sorted(self.identity_assignments.items()),
            "profiles": sorted(
                (
                    self._profile_signature(self.profiles.get(name.casefold()))
                    for name in set([*self.assignments.values(), *self.identity_assignments.values(), self.unassigned_voice]) if name
                ),
                key=lambda item: str((item or {}).get("name", "")).casefold(),
            ),
            "narrating_character": self.narrating_character,
            "unassigned_voice": self.unassigned_voice,
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
    ) -> tuple[list[str], str | None, str]:
        manual = self._assignment_for_span(text, start, end, dialogue_assignments)
        if manual:
            speakers = assignment_speakers(manual)
            if speakers:
                return (
                    speakers,
                    (str(manual.get("multi_speaker_mode") or "chorus").strip().lower()),
                    str(manual.get("series") or "").strip(),
                )

        speaker = self._speaker_for(text, start, end, last_speaker)
        return ([speaker] if speaker else []), None, ""

    def _speaker_for(self, text: str, start: int, end: int, last_speaker: str | None) -> str | None:
        candidate_names = set(self.assignments.keys())
        # Remove ambiguous names even when a legacy name-only assignment still
        # exists in an older project. Otherwise that stale key bypasses the
        # series-aware candidate guard and may select the wrong character.
        for name, series_names in self._identity_series_by_name.items():
            if len(series_names) > 1:
                candidate_names.discard(name)
            else:
                candidate_names.add(name)
        return infer_speaker_for_quote(
            text,
            start,
            end,
            sorted(candidate_names),
            narrator_name=self.narrating_character or None,
            last_speaker=last_speaker,
        )

    @staticmethod
    def _normalized_text_with_map(value: str) -> tuple[str, list[int]]:
        """Normalize text for source matching while mapping tokens to source offsets."""
        normalized: list[str] = []
        source_positions: list[int] = []
        pending_space_at: int | None = None
        for source_index, source_char in enumerate(str(value or "")):
            expanded = unicodedata.normalize("NFKC", source_char).casefold()
            for char in expanded:
                if char.isalnum() or char == "_":
                    if pending_space_at is not None and normalized:
                        normalized.append(" ")
                        source_positions.append(pending_space_at)
                    pending_space_at = None
                    normalized.append(char)
                    source_positions.append(source_index)
                elif normalized:
                    pending_space_at = source_index
        while normalized and normalized[-1] == " ":
            normalized.pop()
            source_positions.pop()
        return "".join(normalized), source_positions

    @classmethod
    def _context_match_length(cls, expected: str, actual: str, *, before: bool) -> int:
        expected_norm, _ = cls._normalized_text_with_map(expected)
        actual_norm, _ = cls._normalized_text_with_map(actual)
        for size in range(min(len(expected_norm), 80), 11, -1):
            sample = expected_norm[-size:] if before else expected_norm[:size]
            if (actual_norm.endswith(sample) if before else actual_norm.startswith(sample)):
                return size
        return 0

    def split_for_cast(self, text: str, fallback_voice: str | None, dialogue_assignments=None):
        """Split dialogue and apply source-bound subturns after narration normalization."""
        spans = _all_dialogue_spans(text)
        assignments = [dict(item) for item in (dialogue_assignments or []) if isinstance(item, dict)]
        valid_assignments = []
        for assignment in assignments:
            if not assignment_speakers(assignment):
                continue
            passage_id = str(assignment.get("passage_id") or "").strip()
            try:
                start, end = int(assignment.get("start", -1)), int(assignment.get("end", -1))
            except (TypeError, ValueError, OverflowError):
                if passage_id:
                    raise ValueError(
                        "Confirmed dialogue assignment for passage '%s' has invalid source offsets. "
                        "Refresh Character Studio and review the passage before generating audio." % passage_id
                    )
                continue
            exact = str(assignment.get("text") or "")
            if start < 0 or end <= start or not exact.strip():
                if passage_id:
                    raise ValueError(
                        "Confirmed dialogue assignment for passage '%s' has no valid source text or offsets. "
                        "Refresh Character Studio and review the passage before generating audio." % passage_id
                    )
                continue
            if not assignment.get("source_passage_id") and text[start:end] != exact:
                expected_norm, _ = self._normalized_text_with_map(exact)
                prepared_norm, prepared_map = self._normalized_text_with_map(text)
                positions = []
                if expected_norm:
                    search_from = 0
                    while True:
                        found = prepared_norm.find(expected_norm, search_from)
                        if found < 0:
                            break
                        positions.append(found)
                        search_from = found + 1
                if len(positions) != 1:
                    if passage_id:
                        reason = "could not be found" if not positions else "matches more than once"
                        raise ValueError(
                            "Confirmed dialogue assignment for passage '%s' %s after TTS text normalization. "
                            "The character route is ambiguous, so generation was stopped instead of using a fallback voice. "
                            "Refresh the workbook or review the passage segmentation before retrying."
                            % (passage_id, reason)
                        )
                    continue
                mapped_start_index = positions[0]
                mapped_end_index = mapped_start_index + len(expected_norm) - 1
                if mapped_end_index >= len(prepared_map):
                    if passage_id:
                        raise ValueError(
                            "Confirmed dialogue assignment for passage '%s' exceeds the prepared TTS text. "
                            "Refresh Character Studio and review the passage before generating audio." % passage_id
                        )
                    continue
                start = prepared_map[mapped_start_index]
                end = prepared_map[mapped_end_index] + 1
                assignment = dict(assignment)
                exact = text[start:end]
                assignment.update({"start": start, "end": end, "text": exact})
            valid_assignments.append((start, end, exact, assignment))

        # App offsets refer to original chapter text. TTS receives cleaned narration,
        # so map each corrected parent and its turns through normalization first.
        split_groups: dict[str, list[tuple[int, int, str, dict]]] = {}
        for item in valid_assignments:
            assignment = item[3]
            parent_id = str(assignment.get("source_passage_id") or "").strip()
            parent_text = str(assignment.get("source_passage_text") or "")
            if parent_id and parent_text:
                split_groups.setdefault(parent_id, []).append(item)

        router_assignments = [dict(item) for item in assignments]
        replaced_parent_ids: set[str] = set()
        for parent_id, children in split_groups.items():
            parent_text = str(children[0][3].get("source_passage_text") or "")
            if any(str(child[3].get("source_passage_text") or "") != parent_text for child in children):
                raise ValueError("Corrected dialogue parent '%s' has inconsistent saved source text." % parent_id)
            parent_norm, parent_map = self._normalized_text_with_map(parent_text)
            target_norm, target_map = self._normalized_text_with_map(text)
            if not parent_norm or not target_map:
                raise ValueError("Corrected dialogue parent '%s' is empty after TTS text normalization." % parent_id)

            candidates = []
            search_from = 0
            while True:
                found = target_norm.find(parent_norm, search_from)
                if found < 0:
                    break
                candidates.append(found)
                search_from = found + 1
            if not candidates:
                raise ValueError(
                    "Corrected dialogue parent '%s' could not be matched to prepared narration text. "
                    "Refresh the chapter's dialogue segmentation before generating audio." % parent_id
                )
            before_context = str(children[0][3].get("source_context_before") or "")
            after_context = str(children[0][3].get("source_context_after") or "")
            scored = []
            for found in candidates:
                target_start = target_map[found]
                target_end = target_map[found + len(parent_norm) - 1] + 1
                before_score = self._context_match_length(before_context, text[:target_start], before=True)
                after_score = self._context_match_length(after_context, text[target_end:], before=False)
                scored.append((before_score + after_score, before_score, after_score, found))
            best_score = max((item[0], item[1], item[2]) for item in scored)
            best = [item for item in scored if (item[0], item[1], item[2]) == best_score]
            if len(candidates) > 1:
                if best_score[0] == 0 or len(best) != 1:
                    raise ValueError(
                        "Corrected dialogue parent '%s' appears more than once and its context does not "
                        "identify one safe occurrence. Review the chapter before generation." % parent_id
                    )
                parent_match = best[0][3]
            else:
                parent_match = candidates[0]

            parent_target_start = target_map[parent_match]
            parent_target_end = target_map[parent_match + len(parent_norm) - 1] + 1
            children.sort(key=lambda item: int(item[3].get("source_start_relative", 0)))
            mapped_children = []
            for _absolute_start, _absolute_end, child_text, assignment in children:
                try:
                    relative_start = int(assignment.get("source_start_relative", -1))
                    relative_end = int(assignment.get("source_end_relative", -1))
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("Corrected subturn in parent '%s' has invalid original offsets." % parent_id)
                if relative_start < 0 or relative_end <= relative_start or relative_end > len(parent_text):
                    raise ValueError("Corrected subturn in parent '%s' is outside its original source passage." % parent_id)
                if parent_text[relative_start:relative_end] != child_text:
                    raise ValueError("Corrected subturn in parent '%s' no longer matches its exact source text." % parent_id)
                relative_indices = [
                    index for index, source_index in enumerate(parent_map)
                    if relative_start <= source_index < relative_end
                ]
                if not relative_indices:
                    raise ValueError("Corrected subturn in parent '%s' contains no spoken words after normalization." % parent_id)
                normalized_child = parent_norm[relative_indices[0]:relative_indices[-1] + 1].strip()
                if not normalized_child:
                    raise ValueError("Corrected subturn in parent '%s' contains no spoken words after normalization." % parent_id)
                target_start_index = parent_match + relative_indices[0]
                target_end_index = parent_match + relative_indices[-1]
                if target_end_index >= len(target_map):
                    raise ValueError("Corrected subturn in parent '%s' exceeds the prepared chapter text." % parent_id)

                mapped_start = target_map[target_start_index]
                mapped_end = target_map[target_end_index] + 1
                opening_chars = "“‘「『\"'([{"
                closing_chars = "”’」』\"')]}.,!?;:…"
                while mapped_start > parent_target_start and text[mapped_start - 1] in opening_chars:
                    mapped_start -= 1
                while mapped_end < parent_target_end and text[mapped_end] in closing_chars:
                    mapped_end += 1
                if not parent_target_start <= mapped_start < mapped_end <= parent_target_end:
                    raise ValueError("Corrected subturn in parent '%s' mapped outside its parent passage." % parent_id)
                mapped_text = text[mapped_start:mapped_end]
                mapped_assignment = dict(assignment)
                mapped_assignment.update({"start": mapped_start, "end": mapped_end, "text": mapped_text})
                mapped_children.append((mapped_start, mapped_end, mapped_text, mapped_assignment))

            if len(mapped_children) < 2:
                raise ValueError("Corrected dialogue parent '%s' requires at least two subturns." % parent_id)
            if any(mapped_children[i][0] < mapped_children[i - 1][1] for i in range(1, len(mapped_children))):
                raise ValueError("Corrected dialogue parent '%s' has overlapping mapped turns after TTS normalization." % parent_id)
            spans = [span for span in spans if not (span[0] < parent_target_end and parent_target_start < span[1])]
            spans.extend((start, end, raw) for start, end, raw, _assignment in mapped_children)
            router_assignments.extend(item[3] for item in mapped_children)
            replaced_parent_ids.add(parent_id)

        spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        for start, end, exact, assignment in valid_assignments:
            if str(assignment.get("source_passage_id") or "") in replaced_parent_ids:
                continue
            if any(span_start <= start and end <= span_end for span_start, span_end, _ in spans):
                continue
            if any(start < span_end and span_start < end for span_start, span_end, _ in spans):
                continue
            spans.append((start, end, exact))
        spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        if not spans:
            return [(text, fallback_voice)]

        parts = []
        cursor = 0
        last_speaker = None
        alternating_voice_index = 0
        for start, end, _dialogue in spans:
            if start > cursor:
                parts.append((text[cursor:start], fallback_voice))
            speakers, multi_mode, assignment_series = self._speakers_for(
                text, start, end, last_speaker, dialogue_assignments=router_assignments
            )
            assigned_voices = []
            for speaker in speakers:
                name_key = str(speaker or "").strip().casefold()
                identity_key = character_identity_key(speaker, assignment_series) if assignment_series else ""
                known_series = self._identity_series_by_name.get(name_key, set())
                if identity_key and identity_key in self.identity_assignments:
                    profile_name = self.identity_assignments[identity_key]
                elif assignment_series and known_series:
                    profile_name = ""
                elif len(known_series) > 1:
                    profile_name = ""
                else:
                    profile_name = self.assignments.get(name_key, "")
                if profile_name:
                    assigned_voices.append(profile_name)
                elif self.unassigned_voice:
                    assigned_voices.append(self.unassigned_voice)
            if assigned_voices:
                if len(assigned_voices) > 1 and multi_mode == "alternating":
                    voice = assigned_voices[alternating_voice_index % len(assigned_voices)]
                    alternating_voice_index += 1
                elif len(assigned_voices) > 1 and multi_mode != "sequential":
                    voice = assigned_voices
                else:
                    voice = assigned_voices[0]
            else:
                voice = self.unassigned_voice or fallback_voice
            if speakers:
                last_speaker = speakers[-1].casefold()

            dialogue = text[start:end].strip()
            for _ in range(3):
                stripped = dialogue.strip()
                changed = False
                for opening, closing in (("(", ")"), ("{", "}"), ("[", "]")):
                    if stripped.startswith(opening) and stripped.endswith(closing) and len(stripped) > 2:
                        dialogue = stripped[1:-1].strip()
                        changed = True
                        break
                if not changed:
                    break
            repeated_marker = re.fullmatch(r'\s*"{2,}(.*?)"{2,}\s*', dialogue, flags=re.S)
            if repeated_marker:
                dialogue = repeated_marker.group(1).strip()
            else:
                if len(dialogue) >= 2 and (
                    (dialogue[0], dialogue[-1]) in {
                        ("“", "”"), ('"', '"'), ("「", "」"), ("『", "』"),
                        ("‘", "’"), ("'", "'"),
                    }
                ):
                    dialogue = dialogue[1:-1].strip()
                else:
                    if dialogue[:1] in {"“", "‘", "「", "『", '"', "'"}:
                        dialogue = dialogue[1:].strip()
                    if dialogue[-1:] in {"”", "’", "」", "』", '"', "'"}:
                        dialogue = dialogue[:-1].strip()
                    stripped = dialogue.lstrip(" \t")
                    if stripped and stripped[0] in "—–-":
                        dialogue = stripped[1:].strip()
            if dialogue:
                if assigned_voices and len(assigned_voices) > 1 and multi_mode == "sequential":
                    for assigned_voice in assigned_voices:
                        parts.append((dialogue, assigned_voice))
                else:
                    parts.append((dialogue, voice))
            cursor = end
        if cursor < len(text):
            parts.append((text[cursor:], fallback_voice))
        return [(segment.strip(), voice) for segment, voice in parts if segment.strip()]

    def close(self) -> None:
        providers = [self.narrator_provider, *[item[0] for item in self._providers.values()]]
        seen = set()
        for provider in providers:
            if id(provider) in seen:
                continue
            seen.add(id(provider))
            close = getattr(provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    # One failed child shutdown must not prevent the remaining
                    # heavyweight workers from being released.
                    continue

    def _provider_cache_key(self, profile_name: str, profile: VoiceProfile) -> str:
        backend = self.backend_override if self.backend_override != "automatic" else (profile.backend or "automatic")
        if profile.provider == "qwen-character" and str(profile.qwen_mode or "custom").casefold() in {"custom", "clone", "design"}:
            return "shared:qwen:" + json.dumps([
                backend, profile.model_id or "auto", profile.qwen_mode or "custom",
                get_qwen_model_preference(),
            ], separators=(",", ":"))
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

    @property
    def recommended_batch_size(self) -> int:
        """Use conservative Qwen batching for both narrator and cast chapters."""
        if not any(
            profile.provider == "qwen-character"
            and str(profile.qwen_mode or "custom").casefold() == "design"
            for profile in self.profiles.values()
        ):
            return int(getattr(self.narrator_provider, "recommended_batch_size", 1) or 1)
        try:
            from app.tts.qwen_character_runtime import best_accelerator
            device = best_accelerator()
            return 2 if device.memory_gb >= 12.0 and (
                device.supported or device.backend == "cuda-candidate"
            ) else 1
        except Exception:
            return 1

    def _provider_for_voice(self, voice: str | None):
        profile_name = str(voice or "").casefold()
        profile = self.profiles.get(profile_name)
        if profile is None:
            assigned_profile_names = {
                str(name).strip().casefold()
                for name in (*self.assignments.values(), *self.identity_assignments.values())
                if str(name).strip()
            }
            if profile_name and profile_name in assigned_profile_names:
                raise RuntimeError(
                    f"The assigned character voice profile '{voice}' is unavailable. "
                    "Open Character Studio and assign an available saved voice profile, then retry."
                )
            return self.narrator_provider, self.narrator_voice

        cache_key = self._provider_cache_key(profile_name, profile)
        cached = self._providers.get(cache_key)
        if cached is None:
            cached = provider_from_profile(profile)
            provider, provider_voice = cached
            if self.backend_override != "automatic" and hasattr(provider, "backend"):
                provider.backend = self.backend_override
            child_callback = getattr(provider, "set_status_callback", None)
            if callable(child_callback):
                child_callback(self._status_callback)
            cached = (provider, provider_voice)
            self._providers[cache_key] = cached
        provider, provider_voice = cached
        if cache_key.startswith(("shared:qwen:", "shared:chatterbox:")):
            self._configure_profile_request(provider, profile)
            provider_voice = profile.voice_id
        return provider, provider_voice

    def is_qwen_voice(self, voice: str | list[str] | tuple[str, ...] | None = None) -> bool:
        """Identify Qwen profiles, including each member of a multi-voice chorus."""
        if isinstance(voice, (list, tuple, set)):
            return any(self.is_qwen_voice(item) for item in voice)
        profile = self.profiles.get(str(voice or "").casefold())
        if profile is not None:
            return str(profile.provider or "").casefold() == "qwen-character"
        return str(getattr(self.narrator_provider, "provider_id", "") or "").casefold() == "qwen-character"

    def is_character_voice(self, voice: str | list[str] | tuple[str, ...] | None = None) -> bool:
        """Identify any saved cast profile, regardless of its TTS model provider."""
        if isinstance(voice, (list, tuple, set)):
            return any(self.is_character_voice(item) for item in voice)
        return str(voice or "").strip().casefold() in self.profiles

    def set_generation_context(self, context: dict | None = None) -> None:
        """Retain the current story window until the selected child voice is resolved."""
        context = context if isinstance(context, dict) else {}
        self._generation_context = {
            "before": str(context.get("before") or "")[-1200:],
            "after": str(context.get("after") or "")[:1200],
        }

    def set_batch_contexts(self, contexts: list[dict] | None = None) -> None:
        """Retain a context pair per item until the child provider is resolved."""
        self._batch_contexts = [
            {
                "before": str(row.get("before") or "")[-1200:],
                "after": str(row.get("after") or "")[:1200],
            }
            for row in (contexts or []) if isinstance(row, dict)
        ]

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        provider, provider_voice = self._provider_for_voice(voice)
        context_setter = getattr(provider, "set_generation_context", None)
        if callable(context_setter):
            context_setter(dict(self._generation_context))
        return provider.synthesize(text, output_path, provider_voice)

    def synthesize_batch(
        self,
        items: list[tuple[str, Path]],
        voice: str | None = None,
    ) -> list[Path]:
        """Batch adjacent chunks only for one resolved speaker profile."""
        if not items:
            return []
        provider, provider_voice = self._provider_for_voice(voice)
        contexts = (
            self._batch_contexts
            if len(self._batch_contexts) == len(items)
            else [dict(self._generation_context) for _ in items]
        )
        self._batch_contexts = []
        batch = getattr(provider, "synthesize_batch", None)
        if callable(batch):
            batch_context_setter = getattr(provider, "set_batch_contexts", None)
            if callable(batch_context_setter):
                batch_context_setter(contexts)
            return batch(items)
        outputs = []
        for (text, output), context in zip(items, contexts):
            context_setter = getattr(provider, "set_generation_context", None)
            if callable(context_setter):
                context_setter(context)
            outputs.append(provider.synthesize(text, output, provider_voice))
        return outputs
