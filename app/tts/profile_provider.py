from pathlib import Path
import hashlib
import json

from app.tts.voice_profile import VoiceProfile
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.providers.piper import PiperProvider
from app.tts.providers.kokoro import KokoroProvider
from app.tts.providers.chatterbox import ChatterboxProvider
from app.tts.providers.edge_tts import EdgeTTSProvider
from app.tts.providers.elevenlabs import ElevenLabsProvider
from app.tts.providers.qwen_character import QwenCharacterProvider


def provider_from_profile(profile: VoiceProfile):
    if profile.provider == "windows-sapi":
        return SystemSAPIProvider(), profile.voice_id

    if profile.provider == "edge-tts":
        return EdgeTTSProvider(), profile.voice_id

    if profile.provider == "elevenlabs":
        return ElevenLabsProvider(), profile.voice_id

    if profile.provider == "qwen-character":
        return (
            QwenCharacterProvider(
                voice_id=profile.voice_id,
                language=profile.language or "English",
                instruct=profile.qwen_prompt or profile.notes,
                backend=profile.backend,
                model_kind=profile.model_id or "auto",
                reference_audio=(
                    Path(profile.sample_path).expanduser()
                    if profile.sample_path else None
                ),
                reference_text=profile.reference_text or "",
                qwen_mode=profile.qwen_mode or "custom",
                qwen_seed=profile.qwen_seed,
                qwen_anchor_path=(
                    Path(profile.qwen_anchor_path).expanduser()
                    if profile.qwen_anchor_path else None
                ),
                qwen_anchor_text=profile.qwen_anchor_text or "",
                qwen_profile_id=profile.qwen_profile_id or "",
            ),
            profile.voice_id,
        )

    if profile.provider == "piper":
        return PiperProvider(backend=profile.backend), profile.voice_id

    if profile.provider == "kokoro":
        return KokoroProvider(backend=profile.backend), profile.voice_id

    if profile.provider == "chatterbox":
        reference = Path(profile.sample_path).expanduser() if profile.sample_path else None
        if reference is not None:
            try:
                reference = reference.resolve()
            except OSError:
                reference = reference.absolute()
        if reference is None or not reference.is_file():
            raise RuntimeError(
                f"Custom voice profile '{profile.name}' has no valid reference audio. "
                "Reload or re-import the custom voice."
            )
        return (
            ChatterboxProvider(
                reference_audio=reference,
                backend=profile.backend,
                language=profile.language,
                multilingual=profile.model_id == "chatterbox-multilingual",
                exaggeration=profile.exaggeration,
                cfg_weight=profile.cfg_weight,
            ),
            profile.voice_id,
        )

    raise ValueError(f"Unsupported voice provider: {profile.provider}")



class ProfileBoundProvider:
    """Delegate synthesis while making the selected saved profile part of cache identity."""

    def __init__(self, provider, profile: VoiceProfile):
        self._provider = provider
        self.profile = profile

    def __getattr__(self, name):
        return getattr(self._provider, name)

    def voices(self):
        return self._provider.voices()

    def synthesize(self, text, output_path, voice=None):
        return self._provider.synthesize(text, output_path, voice=voice)

    def generation_signature(self) -> str:
        from dataclasses import asdict

        profile_data = asdict(self.profile)
        for key, raw_path in (("sample_audio_sha256", self.profile.sample_path),
                              ("anchor_audio_sha256", self.profile.qwen_anchor_path)):
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
            profile_data[key] = digest
        engine_signature = getattr(self._provider, "generation_signature", None)
        engine_data = engine_signature() if callable(engine_signature) else (
            f"{self._provider.__class__.__module__}.{self._provider.__class__.__qualname__}"
        )
        payload = {"profile": profile_data, "engine": engine_data}
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
