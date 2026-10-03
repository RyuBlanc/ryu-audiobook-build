from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from app.core.paths import settings_root
from ..base import TTSProvider
import imageio_ffmpeg
import subprocess


class ElevenLabsProvider(TTSProvider):
    """Premium online ElevenLabs TTS adapter using the public REST API.

    The API key is kept locally in Settings/elevenlabs.json or can be supplied
    through ELEVENLABS_API_KEY. No key is bundled with the application.
    """

    provider_id = "elevenlabs"
    is_online_provider = True
    stop_on_failure = True
    request_timeout_seconds = 180
    API_BASE = "https://api.elevenlabs.io/v1"
    KEY_FILE = settings_root() / "elevenlabs.json"

    def __init__(self, api_key: str | None = None, model_id: str = "eleven_v4"):
        self.api_key = (api_key or self.load_api_key() or "").strip()
        self.model_id = model_id
        if not self.api_key:
            raise RuntimeError(
                "ElevenLabs API key is not configured. In Voice & Narration, choose "
                "Premium Online Voices and use Set API Key."
            )

    @classmethod
    def load_api_key(cls) -> str:
        env = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        if env:
            return env
        try:
            if cls.KEY_FILE.exists():
                data = json.loads(cls.KEY_FILE.read_text(encoding="utf-8"))
                return str(data.get("api_key") or "").strip()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return ""

    @classmethod
    def save_api_key(cls, value: str) -> None:
        cls.KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.KEY_FILE.write_text(
            json.dumps({"api_key": str(value or "").strip()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def clear_api_key(cls) -> None:
        try:
            cls.KEY_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    @classmethod
    def _request(cls, method: str, url: str, api_key: str, payload: bytes | None = None, content_type: str = "application/json"):
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "xi-api-key": api_key,
                "Content-Type": content_type,
                "Accept": "application/json",
                "User-Agent": "Ryu-Audiobook/0.3.2",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=cls.request_timeout_seconds) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if exc.code in {401, 403}:
                raise RuntimeError("ElevenLabs API key was rejected. Check the key in Voice & Narration.") from exc
            if exc.code == 429:
                raise RuntimeError("ElevenLabs rate/credit limit was reached. Check your ElevenLabs account.") from exc
            raise RuntimeError(f"ElevenLabs request failed ({exc.code}): {detail[-1500:]}") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError(f"ElevenLabs network request failed: {exc}") from exc

    @staticmethod
    def _character_archetype_hint(style: str, temperament: str) -> str:
        value = f"{str(style or '').casefold()} {str(temperament or '').casefold()}"
        if "anime" in value:
            if "heroic" in value:
                return "Bright shonen-style young hero energy with confident determination and emotional lifts."
            if "villain" in value or "ominous" in value:
                return "Elegant anime antagonist presence with controlled menace, low warmth and precise diction."
            if "mischievous" in value:
                return "Playful anime rival energy, teasing confidence and quick emotional reactions."
            if "calm" in value or "cinematic" in value:
                return "Cool anime mentor or strategist presence with restrained intensity and cinematic phrasing."
            if "warm" in value:
                return "Kind anime healer or gentle heroine quality with soft warmth and reassuring delivery."
            return "Expressive anime character performance with clear English diction and distinct personality."
        if "cartoon" in value:
            if "villain" in value or "ominous" in value:
                return "Stylized animated villain energy with playful menace and crisp comic timing."
            if "mischievous" in value:
                return "Fast, cheeky cartoon sidekick energy with elastic emotional reactions."
            if "calm" in value:
                return "Warm animated storyteller quality with polished family-friendly delivery."
            return "Distinct animated-cartoon character acting with playful timing and expressive reactions."

        return "Distinct fictional character voice with stable identity across long-form narration."

    @classmethod
    def design_character_voice(
        cls,
        style: str,
        gender: str = "female",
        age: str = "young adult",
        temperament: str = "expressive",
        model_id: str = "eleven_ttv_v3",
    ) -> list[dict]:
        """Generate premium character-voice previews through ElevenLabs Voice Design.

        The generated previews remain local until the user explicitly chooses
        one and creates it in their ElevenLabs voice library.
        """
        api_key = cls.load_api_key()
        if not api_key:
            raise RuntimeError("Set the ElevenLabs API key before generating a premium character voice.")

        presets = {
            "anime": (
                "Anime character voice, dynamic Japanese-animation-inspired English delivery. "
                "Clear diction, expressive emotion, youthful performance, cinematic character acting."
            ),
            "cartoon": (
                "High-quality English cartoon character voice. "
                "Distinctive animated performance, clear diction, playful timing and strong personality."
            ),
        }
        prompt_base = presets.get(str(style or "").casefold(), presets["anime"])
        gender_phrase = str(gender or "female").strip().casefold()
        age_phrase = str(age or "young adult").strip()
        temperament_phrase = str(temperament or "expressive").strip()
        archetype = str(self._character_archetype_hint(style, temperament)).strip()
        description = (
            f"{prompt_base} Speaker: {age_phrase} {gender_phrase}. "
            f"Temperament: {temperament_phrase}. {archetype} "
            "Designed for long-form audiobook dialogue and frequent character scenes; "
            "natural breath, stable identity, emotionally controlled without sounding synthetic."
        )
        sample = (
            "I finally found you! Wait—don't move. The whole town is counting on us, "
            "and this time I'm not running away. Come on, let's finish this together."
            if str(style or "").casefold() == "anime"
            else
            "Well, well, look who wandered into my little corner of trouble! "
            "Relax, friend—I've got a plan, and for once it might actually work."
        )
        payload = json.dumps(
            {
                "model_id": model_id,
                "voice_description": description,
                "text": sample,
                "auto_generate_text": False,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        raw, _ = cls._request(
            "POST",
            f"{cls.API_BASE}/text-to-voice/design?output_format=mp3_22050_32",
            api_key,
            payload,
        )
        data = json.loads(raw.decode("utf-8"))
        previews = data.get("previews", []) if isinstance(data, dict) else []
        cleaned: list[dict] = []
        for index, preview in enumerate(previews, 1):
            if not isinstance(preview, dict):
                continue
            encoded = str(preview.get("audio_base_64") or "").strip()
            generated_id = str(preview.get("generated_voice_id") or "").strip()
            if not encoded or not generated_id:
                continue
            cleaned.append(
                {
                    "index": index,
                    "generated_voice_id": generated_id,
                    "audio_base_64": encoded,
                    "duration_secs": preview.get("duration_secs"),
                    "language": preview.get("language") or "en",
                    "style": style,
                    "description": description,
                    "sample_text": sample,
                    "gender": gender,
                    "age": age,
                    "temperament": temperament,
                    "model_id": model_id,
                }
            )
        if not cleaned:
            raise RuntimeError("ElevenLabs did not return any voice-design previews.")
        return cleaned

    @classmethod
    def create_designed_voice(
        cls,
        generated_voice_id: str,
        voice_name: str,
        voice_description: str,
        style: str,
        gender: str,
        age: str,
    ) -> dict:
        """Create a selected Voice Design preview as a voice in My Voices."""
        api_key = cls.load_api_key()
        if not api_key:
            raise RuntimeError("Set the ElevenLabs API key before saving a premium character voice.")
        payload = json.dumps(
            {
                "voice_name": voice_name,
                "voice_description": voice_description,
                "generated_voice_id": generated_voice_id,
                "labels": {
                    "language": "en",
                    "gender": str(gender or "unknown"),
                    "age": str(age or "unknown"),
                    "description": f"{str(style or 'character').title()} character voice",
                    "use_case": "audiobook character",
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        raw, _ = cls._request(
            "POST",
            f"{cls.API_BASE}/text-to-voice",
            api_key,
            payload,
        )
        data = json.loads(raw.decode("utf-8"))
        voice_id = str(data.get("voice_id") or "").strip() if isinstance(data, dict) else ""
        if not voice_id:
            raise RuntimeError("ElevenLabs did not return a voice ID after creating the premium character voice.")
        return data

    @classmethod
    def fetch_voice_metadata(cls, refresh: bool = False) -> list[dict]:
        # A small local cache keeps the voice picker usable between sessions,
        # but synthesis itself remains online.
        cache = settings_root() / "elevenlabs_voices.json"
        if not refresh and cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass

        key = cls.load_api_key()
        if not key:
            return []
        raw, _ = cls._request("GET", f"{cls.API_BASE}/voices", key, None)
        data = json.loads(raw.decode("utf-8"))
        voices = data.get("voices", []) if isinstance(data, dict) else []
        cleaned = []
        for voice in voices:
            labels = voice.get("labels") or {}
            cleaned.append(
                {
                    "voice_id": str(voice.get("voice_id") or ""),
                    "name": str(voice.get("name") or ""),
                    "category": str(voice.get("category") or ""),
                    "language": str(labels.get("language") or voice.get("fine_tuning", {}).get("language") or "en"),
                    "accent": str(labels.get("accent") or ""),
                    "gender": str(labels.get("gender") or "Neutral"),
                    "description": str(labels.get("description") or ""),
                    "use_case": str(labels.get("use_case") or ""),
                }
            )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        return cleaned

    def voices(self) -> list[str]:
        return [str(item.get("voice_id")) for item in self.fetch_voice_metadata() if item.get("voice_id")]

    def synthesize(self, text: str, output_path: Path, voice: str | None = None) -> Path:
        if not voice:
            raise ValueError("An ElevenLabs voice must be selected.")
        if not text.strip():
            raise ValueError("ElevenLabs cannot synthesize empty text.")

        query = urllib.parse.urlencode({"output_format": "mp3_44100_128"})
        url = f"{self.API_BASE}/text-to-speech/{urllib.parse.quote(voice, safe='')}" + f"?{query}"
        payload = json.dumps(
            {
                "text": text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.78,
                    "use_speaker_boost": True,
                },
                "apply_text_normalization": "auto",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        raw, _ = self._request("POST", url, self.api_key, payload)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(prefix="ryu-eleven-", suffix=".mp3", delete=False) as handle:
            handle.write(raw)
            mp3_path = Path(handle.name)
        try:
            if output_path.suffix.lower() == ".mp3":
                mp3_path.replace(output_path)
                return output_path

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(mp3_path),
                    "-ar", "24000", "-ac", "1",
                    str(output_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        finally:
            mp3_path.unlink(missing_ok=True)

        if not output_path.exists() or output_path.stat().st_size < 1024:
            raise RuntimeError("ElevenLabs returned audio, but the converted file was invalid.")
        return output_path
