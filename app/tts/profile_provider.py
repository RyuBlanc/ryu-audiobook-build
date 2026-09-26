from pathlib import Path

from app.tts.voice_profile import VoiceProfile
from app.tts.system_sapi import SystemSAPIProvider
from app.tts.providers.piper import PiperProvider
from app.tts.providers.chatterbox import ChatterboxProvider
from app.tts.providers.edge_tts import EdgeTTSProvider


def provider_from_profile(profile: VoiceProfile):
    if profile.provider == "windows-sapi":
        return SystemSAPIProvider(), profile.voice_id

    if profile.provider == "edge-tts":
        return EdgeTTSProvider(), profile.voice_id

    if profile.provider == "piper":
        return PiperProvider(backend=profile.backend), profile.voice_id

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
            ),
            profile.voice_id,
        )

    raise ValueError(f"Unsupported voice provider: {profile.provider}")
