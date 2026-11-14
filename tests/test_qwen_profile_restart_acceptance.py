"""Stage C2 process-restart acceptance for saved Qwen voice identities."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.tts.voice_profile import VoiceProfile, save_profiles


class QwenSavedProfileRestartTests(unittest.TestCase):
    def test_custom_design_and_clone_profiles_keep_identity_after_fresh_process_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            voices = root / "Voices"
            references = voices / "References"
            references.mkdir(parents=True)
            reference_audio = references / "authorized-clone-reference.wav"
            reference_audio.write_bytes(b"authorized reference audio fixture")
            anchor_audio = references / "design-identity-anchor.wav"
            anchor_audio.write_bytes(b"saved VoiceDesign identity anchor")

            profiles = [
                VoiceProfile(
                    name="C2 Saved CustomVoice",
                    provider="qwen-character",
                    voice_id="Ryan",
                    model_id="custom-0.6b",
                    backend="automatic",
                    language="English",
                    authorized=True,
                    qwen_mode="custom",
                    qwen_prompt="Clear, warm audiobook narration.",
                    qwen_seed=6001,
                    qwen_profile_id="c2-custom-profile-id",
                ),
                VoiceProfile(
                    name="C2 Saved VoiceDesign",
                    provider="qwen-character",
                    voice_id="Ryan",
                    model_id="design-1.7b",
                    backend="automatic",
                    language="Japanese",
                    authorized=True,
                    qwen_mode="design",
                    qwen_prompt="Calm and expressive Japanese character voice.",
                    qwen_seed=17001,
                    qwen_anchor_path=str(anchor_audio.resolve()),
                    qwen_anchor_text="A stable identity anchor for the saved voice.",
                    qwen_profile_id="c2-design-profile-id",
                ),
                VoiceProfile(
                    name="C2 Saved Clone",
                    provider="qwen-character",
                    voice_id="Clone",
                    model_id="base-0.6b",
                    backend="automatic",
                    language="English",
                    sample_path=str(reference_audio.resolve()),
                    authorized=True,
                    qwen_mode="clone",
                    qwen_prompt="Preserve the authorized reference speaker identity.",
                    qwen_seed=6002,
                    qwen_profile_id="c2-clone-profile-id",
                ),
            ]

            with (
                patch("app.tts.voice_profile.voices_root", return_value=voices),
                patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]),
            ):
                save_profiles(profiles)

            script = r"""
import json
import sys
from pathlib import Path
import app.tts.voice_profile as catalogue

root = Path(sys.argv[1]).resolve()
catalogue.voices_root = lambda: root
catalogue.builtin_voice_profiles = lambda: []
rows = catalogue.load_profiles()
by_name = {item.name: item for item in rows}
expected = {
    "C2 Saved CustomVoice": {
        "mode": "custom", "profile_id": "c2-custom-profile-id",
        "model_id": "custom-0.6b", "voice_id": "Ryan",
    },
    "C2 Saved VoiceDesign": {
        "mode": "design", "profile_id": "c2-design-profile-id",
        "model_id": "design-1.7b", "voice_id": "Ryan",
    },
    "C2 Saved Clone": {
        "mode": "clone", "profile_id": "c2-clone-profile-id",
        "model_id": "base-0.6b", "voice_id": "Clone",
    },
}
assert set(expected).issubset(by_name), sorted(by_name)
for name, values in expected.items():
    profile = by_name[name]
    assert profile.qwen_mode == values["mode"], (name, profile.qwen_mode)
    assert profile.qwen_profile_id == values["profile_id"], (name, profile.qwen_profile_id)
    assert profile.model_id == values["model_id"], (name, profile.model_id)
    assert profile.voice_id == values["voice_id"], (name, profile.voice_id)
    assert profile.authorized is True, name
    assert profile.backend == "automatic", (name, profile.backend)

design = by_name["C2 Saved VoiceDesign"]
assert design.qwen_prompt.startswith("Calm and expressive")
assert design.qwen_seed == 17001
assert design.language == "Japanese"
assert design.qwen_anchor_text == "A stable identity anchor for the saved voice."
assert Path(design.qwen_anchor_path).is_file()

clone = by_name["C2 Saved Clone"]
assert clone.qwen_prompt.startswith("Preserve the authorized")
assert clone.qwen_seed == 6002
assert Path(clone.sample_path).is_file()

custom = by_name["C2 Saved CustomVoice"]
assert custom.qwen_prompt.startswith("Clear, warm")
assert custom.qwen_seed == 6001

print(json.dumps({"restart_profiles": sorted(expected), "identity_ids_preserved": True}))
"""
            env = os.environ.copy()
            repo_root = Path(__file__).resolve().parents[1]
            env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
            result = subprocess.run(
                [sys.executable, "-B", "-c", script, str(voices)],
                cwd=str(repo_root),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
            self.assertEqual(
                result.returncode,
                0,
                "Fresh-interpreter profile reload failed.\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn('"identity_ids_preserved": true', result.stdout)
            self.assertTrue(reference_audio.is_file())
            self.assertTrue(anchor_audio.is_file())


if __name__ == "__main__":
    unittest.main()
