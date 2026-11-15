"""Stage D2 Qwen profile bundle export and integrity tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
import zipfile

from app.tts.qwen_character_worker import _anchor_path
from app.tts.qwen_profile_bundle import (
    BUNDLE_FORMAT, export_qwen_profiles_bundle, inspect_qwen_profile_bundle,
)
from app.tts.qwen_profile_schema import qwen_design_anchor_cache_path
from app.tts.voice_profile import VoiceProfile


def write_wav(path: Path, seconds: float = 0.08, sample_rate: int = 24000) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = b"\x00\x00" * max(1, int(seconds * sample_rate))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)
    return path.read_bytes()


class QwenProfileBundleExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle_path = self.root / "saved-voices.ryuvoice"
        self.runtime_root = self.root / "runtimes" / "qwen3-tts"

    def tearDown(self):
        self.temporary.cleanup()

    def export_with_runtime(self, profiles, **kwargs):
        with (
            patch("app.tts.qwen_profile_bundle.runtimes_root", return_value=self.runtime_root.parent),
            patch("app.tts.qwen_profile_bundle.get_qwen_model_preference", return_value="0.6b"),
        ):
            return export_qwen_profiles_bundle(profiles, self.bundle_path, **kwargs)

    def test_customvoice_export_contains_portable_profile_without_machine_paths(self):
        profile = VoiceProfile(
            name="Japanese Preset • Ono", provider="qwen-character", voice_id="Ono_Anna",
            model_id="custom-0.6b", language="Japanese", qwen_mode="custom",
            qwen_prompt="Natural Japanese narration.", qwen_seed=1709,
            qwen_profile_id="custom-japanese-identity",
        )
        result = self.export_with_runtime([profile])
        self.assertEqual(result.profile_count, 1)
        self.assertEqual(result.asset_count, 0)
        inspected = inspect_qwen_profile_bundle(result.path)
        self.assertTrue(inspected["integrity_verified"])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            doc = json.loads(archive.read(manifest["profiles"][0]["profile_path"]))
        self.assertEqual(manifest["format"], BUNDLE_FORMAT)
        self.assertFalse(manifest["export"]["model_weights_included"])
        self.assertEqual(doc["profile_record"]["qwen_profile_id"], profile.qwen_profile_id)
        self.assertIsNone(doc["profile_record"]["sample_path"])
        self.assertIsNone(doc["profile_record"]["qwen_anchor_path"])
        self.assertEqual(doc["profile_record"]["language"], "Japanese")

    def test_clone_export_preserves_active_wav_and_original_sidecar_bytes(self):
        profile_dir = self.root / "Voices" / "Novel Hero"
        normalized = profile_dir / "reference.wav"
        normalized_bytes = write_wav(normalized)
        original = profile_dir / "captured-original.mp3"
        original_bytes = b"original-source-audio-bytes-not-transcoded"
        original.write_bytes(original_bytes)
        profile = VoiceProfile(
            name="Novel Hero", provider="qwen-character", voice_id="Novel Hero",
            model_id="base-0.6b", language="English", qwen_mode="clone",
            sample_path=str(normalized), reference_text="The exact reference text.",
            authorized=True, qwen_profile_id="clone-identity-001",
        )
        result = self.export_with_runtime([profile])
        self.assertEqual(result.asset_count, 2)
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assets = manifest["profiles"][0]["assets"]
            by_role = {asset["role"]: asset for asset in assets}
            self.assertEqual(archive.read(by_role["clone_reference_conditioning"]["archive_path"]), normalized_bytes)
            self.assertEqual(archive.read(by_role["clone_reference_original"]["archive_path"]), original_bytes)
            self.assertEqual(by_role["clone_reference_conditioning"]["binding"], "sample_path")
            self.assertEqual(by_role["clone_reference_original"]["source_filename"], original.name)
        self.assertTrue(inspect_qwen_profile_bundle(result.path)["integrity_verified"])

    def test_voicedesign_export_finds_same_cache_anchor_as_worker(self):
        profile = VoiceProfile(
            name="Saved Japanese Design", provider="qwen-character", voice_id="design-jp",
            model_id="design-1.7b", language="Japanese", qwen_mode="design",
            qwen_prompt="A calm Japanese anime narrator.", qwen_seed=17001,
            qwen_anchor_text="これは保存された参照文です。", qwen_profile_id="design-jp-identity",
        )
        request = {
            "speaker": profile.voice_id, "language": profile.language,
            "instruct": profile.qwen_prompt, "seed": profile.qwen_seed,
            "anchor_text": profile.qwen_anchor_text, "profile_id": profile.qwen_profile_id,
        }
        worker_path = _anchor_path(self.runtime_root, request, "neutral")
        shared_path = qwen_design_anchor_cache_path(
            self.runtime_root, speaker=profile.voice_id, language=profile.language,
            instruct=profile.qwen_prompt, seed=profile.qwen_seed,
            anchor_text=profile.qwen_anchor_text, profile_id=profile.qwen_profile_id,
            style="neutral",
        )
        self.assertEqual(worker_path, shared_path)
        anchor_bytes = write_wav(worker_path)
        result = self.export_with_runtime([profile])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            anchor = next(a for a in manifest["profiles"][0]["assets"]
                          if a["role"] == "voicedesign_identity_anchor_derived")
            self.assertEqual(archive.read(anchor["archive_path"]), anchor_bytes)
            self.assertEqual(anchor["identity"]["expression_bank_version"], "v9-language-matched-anchor-direction")
        self.assertTrue(inspect_qwen_profile_bundle(result.path)["integrity_verified"])

    def test_missing_cached_anchor_is_not_misrepresented_as_never_generated(self):
        profile = VoiceProfile(
            name="No Cached Anchor", provider="qwen-character", voice_id="design",
            model_id="design-1.7b", language="English", qwen_mode="design",
            qwen_prompt="Gentle voice.", qwen_profile_id="design-no-cache",
        )
        result = self.export_with_runtime([profile])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            doc = json.loads(archive.read(manifest["profiles"][0]["profile_path"]))
        self.assertEqual(doc["asset_state"]["voice_design_anchor"], "not_found_in_source_cache")
        self.assertEqual(manifest["profiles"][0]["assets"], [])

    def test_explicit_voicedesign_anchor_is_exported_exactly(self):
        explicit = self.root / "explicit-anchor.wav"
        payload = write_wav(explicit)
        profile = VoiceProfile(
            name="Explicit Anchor", provider="qwen-character", voice_id="design",
            model_id="design-1.7b", language="English", qwen_mode="design",
            qwen_prompt="Distinct voice.", qwen_profile_id="design-explicit",
            qwen_anchor_path=str(explicit), qwen_anchor_text="Canonical transcript.",
        )
        result = self.export_with_runtime([profile])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            anchor = manifest["profiles"][0]["assets"][0]
            self.assertEqual(anchor["binding"], "qwen_anchor_path")
            self.assertEqual(archive.read(anchor["archive_path"]), payload)

    def test_unknown_profile_extensions_are_flattened_and_preserved(self):
        profile = VoiceProfile(
            name="Future Extension", provider="qwen-character", voice_id="Ryan",
            qwen_mode="custom", qwen_profile_id="future-ext-id",
            extra_fields={"future_voice_metadata": {"anchor_revision": "v9", "flag": True}},
        )
        result = self.export_with_runtime([profile])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            doc = json.loads(archive.read(manifest["profiles"][0]["profile_path"]))
        self.assertEqual(doc["profile_record"]["future_voice_metadata"], {"anchor_revision": "v9", "flag": True})
        self.assertNotIn("extra_fields", doc["profile_record"])

    def test_multiple_profiles_export_with_distinct_stable_ids(self):
        profiles = [
            VoiceProfile(name="A", provider="qwen-character", voice_id="Ryan",
                         qwen_mode="custom", qwen_profile_id="custom-a"),
            VoiceProfile(name="B", provider="qwen-character", voice_id="Serena",
                         qwen_mode="custom", qwen_profile_id="custom-b"),
        ]
        result = self.export_with_runtime(profiles)
        inspected = inspect_qwen_profile_bundle(result.path)
        self.assertEqual(inspected["profile_count"], 2)
        self.assertEqual({p["profile_id"] for p in inspected["profiles"]}, {"custom-a", "custom-b"})

    def test_unicode_profile_fields_are_preserved(self):
        profile = VoiceProfile(
            name="星野 • 日本語の声", provider="qwen-character", voice_id="Ono_Anna",
            language="日本語", qwen_mode="custom", qwen_prompt="穏やかで自然な声。",
            qwen_profile_id="unicode-jp-profile",
        )
        result = self.export_with_runtime([profile])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            doc = json.loads(archive.read(manifest["profiles"][0]["profile_path"]))
        self.assertEqual(doc["profile_record"]["name"], profile.name)
        self.assertEqual(doc["profile_record"]["language"], "日本語")
        self.assertEqual(doc["profile_record"]["qwen_prompt"], "穏やかで自然な声。")

    def test_clone_without_reference_and_invalid_schema_block_export(self):
        missing = VoiceProfile(
            name="Missing Clone", provider="qwen-character", voice_id="Clone",
            qwen_mode="clone", sample_path=str(self.root / "missing.wav"),
            qwen_profile_id="missing-clone-reference",
        )
        with self.assertRaisesRegex(FileNotFoundError, "missing"):
            self.export_with_runtime([missing])
        for version in (0, 2, "1", None):
            profile = VoiceProfile(
                name="Bad Schema", provider="qwen-character", voice_id="Ryan",
                qwen_mode="custom", qwen_profile_id=f"schema-{str(version)}",
                qwen_profile_schema_version=version,
            )
            with self.subTest(version=version), self.assertRaises(RuntimeError):
                self.export_with_runtime([profile])

    def test_duplicate_ids_and_non_qwen_profiles_are_rejected(self):
        one = VoiceProfile(name="One", provider="qwen-character", voice_id="Ryan",
                           qwen_mode="custom", qwen_profile_id="same-id")
        two = VoiceProfile(name="Two", provider="qwen-character", voice_id="Serena",
                           qwen_mode="custom", qwen_profile_id="same-id")
        with self.assertRaisesRegex(ValueError, "Duplicate Qwen profile ID"):
            self.export_with_runtime([one, two])
        piper = VoiceProfile(name="Piper", provider="piper", voice_id="en_US-amy-medium")
        with self.assertRaisesRegex(ValueError, "Only saved Qwen"):
            self.export_with_runtime([piper])

    def test_missing_anchor_and_invalid_clone_wav_block_export(self):
        missing_anchor = VoiceProfile(
            name="Missing Anchor", provider="qwen-character", voice_id="design",
            qwen_mode="design", qwen_profile_id="missing-explicit-anchor",
            qwen_anchor_path=str(self.root / "absent-anchor.wav"),
        )
        with self.assertRaisesRegex(FileNotFoundError, "missing"):
            self.export_with_runtime([missing_anchor])
        bad = self.root / "bad-reference.wav"
        bad.write_bytes(b"not a wave file")
        clone = VoiceProfile(
            name="Bad Reference", provider="qwen-character", voice_id="Clone",
            qwen_mode="clone", qwen_profile_id="bad-reference", sample_path=str(bad),
        )
        with self.assertRaisesRegex(ValueError, "readable WAV"):
            self.export_with_runtime([clone])

    def test_export_refuses_overwrite_unless_explicitly_allowed(self):
        self.bundle_path.write_bytes(b"keep-this-file")
        profile = VoiceProfile(name="Custom", provider="qwen-character", voice_id="Ryan",
                               qwen_mode="custom", qwen_profile_id="no-overwrite")
        with self.assertRaises(FileExistsError):
            self.export_with_runtime([profile])
        self.assertEqual(self.bundle_path.read_bytes(), b"keep-this-file")

    def test_revision_hash_matches_exact_exported_asset_bytes(self):
        reference = self.root / "reference.wav"
        payload = write_wav(reference)
        profile = VoiceProfile(
            name="Hash Clone", provider="qwen-character", voice_id="Clone",
            qwen_mode="clone", sample_path=str(reference), qwen_profile_id="hash-clone",
        )
        result = self.export_with_runtime([profile])
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            asset = manifest["profiles"][0]["assets"][0]
            self.assertEqual(asset["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(asset["revision_key"], "sample_path")
            self.assertEqual(result.revision_ids[0], manifest["profiles"][0]["revision_id"])

    def test_corrupt_payload_fails_integrity_validation(self):
        profile = VoiceProfile(name="Corrupt", provider="qwen-character", voice_id="Ryan",
                               qwen_mode="custom", qwen_profile_id="corrupt-test")
        self.export_with_runtime([profile])
        corrupted = self.root / "corrupted.ryuvoice"
        with zipfile.ZipFile(self.bundle_path) as source, zipfile.ZipFile(corrupted, "w") as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename.endswith("profile.json"):
                    data += b" "
                target.writestr(item.filename, data)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            inspect_qwen_profile_bundle(corrupted)

    def test_archive_path_traversal_is_rejected(self):
        malicious = self.root / "malicious.ryuvoice"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("manifest.json", "{}")
            archive.writestr("../outside.txt", b"unsafe")
        with self.assertRaisesRegex(ValueError, "unsafe archive path"):
            inspect_qwen_profile_bundle(malicious)

    def test_export_failure_does_not_replace_an_existing_bundle(self):
        self.bundle_path.write_bytes(b"preserve-on-failure")
        profile = VoiceProfile(
            name="Broken Anchor", provider="qwen-character", voice_id="design",
            qwen_mode="design", qwen_profile_id="broken-anchor",
            qwen_anchor_path=str(self.root / "missing.wav"),
        )
        with self.assertRaises(FileNotFoundError):
            self.export_with_runtime([profile], overwrite=True)
        self.assertEqual(self.bundle_path.read_bytes(), b"preserve-on-failure")


if __name__ == "__main__":
    unittest.main()
