from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.chapters.characters import infer_speaker_for_quote
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
    ):
        self.narrator_provider = narrator_provider
        self.narrator_voice = narrator_voice
        self.profiles = {k.casefold(): v for k, v in profiles.items()}
        self.assignments = {k.casefold(): v for k, v in assignments.items() if v}
        self.narrating_character = (narrating_character or "").casefold()
        self._providers: dict[str, tuple[TTSProvider, str]] = {}

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
        spans = []
        for pattern in QUOTE_PATTERNS:
            spans.extend((m.start(), m.end(), m.group(1)) for m in pattern.finditer(text))
        spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))

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
            dialogue = text[start:end].strip()
            if len(dialogue) >= 2 and dialogue[0] in '“"「『' and dialogue[-1] in '”"」』':
                dialogue = dialogue[1:-1].strip()
            parts.append((dialogue, voice))
            cursor = end
        if cursor < len(text):
            parts.append((text[cursor:], fallback_voice))
        return [(t, v) for t, v in parts if t.strip()]

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        profile_name = voice.casefold() if voice else ""
        profile = self.profiles.get(profile_name)
        if profile is None:
            return self.narrator_provider.synthesize(text, output_path, self.narrator_voice)
        cached = self._providers.get(profile_name)
        if cached is None:
            cached = provider_from_profile(profile)
            self._providers[profile_name] = cached
        provider, provider_voice = cached
        return provider.synthesize(text, output_path, provider_voice)
