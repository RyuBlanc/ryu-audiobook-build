from __future__ import annotations

import re
from pathlib import Path

from app.tts.base import TTSProvider
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import VoiceProfile

QUOTE_PATTERNS = [
    re.compile(r'“([^”]+)”'),
    re.compile(r'"([^"]+)"'),
    re.compile(r'「([^」]+)」'),
    re.compile(r'『([^』]+)』'),
]

class CastAwareProvider(TTSProvider):
    """Route explicitly attributed quoted dialogue to assigned profiles."""

    def __init__(self, narrator_provider: TTSProvider, narrator_voice: str | None,
                 profiles: dict[str, VoiceProfile], assignments: dict[str, str]):
        self.narrator_provider = narrator_provider
        self.narrator_voice = narrator_voice
        self.profiles = {k.casefold(): v for k, v in profiles.items()}
        self.assignments = {k.casefold(): v for k, v in assignments.items()}
        self._providers: dict[str, tuple[TTSProvider, str]] = {}

    def voices(self) -> list[str]:
        return [self.narrator_voice] if self.narrator_voice else []

    def _speaker_for(self, text: str, start: int, end: int) -> str | None:
        nearby = text[max(0, start - 220):min(len(text), end + 260)]
        candidates = []
        for name in self.assignments:
            match = re.search(rf'\b{re.escape(name)}\b', nearby, re.I)
            if match:
                candidates.append((abs(match.start() - min(220, start)), name))
        return min(candidates)[1] if candidates else None

    def split_for_cast(self, text: str, fallback_voice: str | None):
        spans = []
        for pattern in QUOTE_PATTERNS:
            spans.extend((m.start(), m.end()) for m in pattern.finditer(text))
        spans.sort()
        if not spans:
            return [(text, fallback_voice)]

        parts = []
        cursor = 0
        for start, end in spans:
            if start > cursor:
                parts.append((text[cursor:start], fallback_voice))
            speaker = self._speaker_for(text, start, end)
            parts.append((text[start:end], self.assignments.get(speaker) if speaker else fallback_voice))
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
