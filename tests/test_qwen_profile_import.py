"""Stage D3 transactional Qwen profile import and recovery acceptance tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from app.tts.qwen_profile_bundle import export_qwen_profiles_bundle
from app.tts.qwen_profile_import import (
    QwenProfileImportConflict,
    QwenProfileImportError,
    import_qwen_profiles_bundle,
    plan_qwen_profiles_import,
    recover_interrupted_qwen_profile_imports,
)
from app.tts.voice_profile import VoiceProfile, load_saved_profiles, profile_record, profiles_file


def write_wav(path: Path, seconds: float = 0.08, sample_rate: int = 24000) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = b"\x00\x00" * max(1, int(seconds * sample_rate))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)
    return path.read_bytes()


class QwenProfileTransactionalImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.voices = self.root / "Voices"
        self.runtimes = self.root / "Models" / "qwen3-tts"
        self.models = self.root / "Models"
        self.bundle = self.root / "selected-profiles.ryuvoice"
        self.voices.mkdir(parents=True)
        self.runtimes.mkdir(parents=True)
        self._patches = [
            patch("app.tts.qwen_profile_import.voices_root", return_value=self.voices),
            patch("app.tts.voice_profile.voices_root", return_value=self.voices),
            patch("app.tts.qwen_profile_import.runtimes_root", return_value=self.models),
            patch("app.tts.qwen_profile_import.models_root", return_value=self.models),
            patch("app.tts.qwen_profile_bundle.runtimes_root", return_value=self.models),
            patch("app.tts.qwen_profile_bundle.get_qwen_model_preference", return_value="0.6b"),
            patch("app.tts.qwen_character_runtime.model_installed", return_value=False),
            patch("app.tts.qwen_character_runtime.runtime_ready", return_value=False),
        ]
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in reversed(self._patches):
            item.stop()
        self.temporary.cleanup()

    def export(self, profiles):
        return export_qwen_profiles_bundle(
            profiles,
            self.bundle,
            source_model_preference="0.6b",
            overwrite=True,
        )

    def catalogue(self):
        path = profiles_file()
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def save_catalogue(self, records):
        profiles_file().parent.mkdir(parents=True, exist_ok=True)
        profiles_file().write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_customvoice_import_preserves_identity_fields_and_unknown_extensions(self):
        profile = VoiceProfile(
            name="Japanese Hero • Ono",
            provider="qwen-character",
            voice_id="Ono_Anna",
            model_id="custom-0.6b",
            language="Japanese",
            qwen_mode="custom",
            qwen_prompt="Calm Japanese narration with precise diction.",
            qwen_seed=1709,
            qwen_profile_id="d3-custom-ono",
            extra_fields={"future_voice_metadata": {"anchor_revision": "v9", "keep": True}},
        )
        self.export([profile])
        plan = plan_qwen_profiles_import(self.bundle)
        self.assertTrue(plan["integrity_verified"])
        self.assertEqual(plan["profiles"][0]["classification"], "new_profile")
        self.assertFalse(plan["profiles"][0]["compatibility"]["runtime_ready"])

        result = import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(result.imported_profile_ids, ("d3-custom-ono",))
        record = self.catalogue()[0]
        self.assertEqual(record["qwen_profile_id"], profile.qwen_profile_id)
        self.assertEqual(record["qwen_mode"], "custom")
        self.assertEqual(record["qwen_prompt"], profile.qwen_prompt)
        self.assertEqual(record["qwen_seed"], 1709)
        self.assertEqual(record["language"], "Japanese")
        self.assertEqual(record["future_voice_metadata"], {"anchor_revision": "v9", "keep": True})
        reloaded = load_saved_profiles()
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0].qwen_profile_id, profile.qwen_profile_id)
        self.assertEqual(reloaded[0].extra_fields["future_voice_metadata"]["keep"], True)

    def test_missing_models_and_runtime_are_reported_without_mutating_backend_preference(self):
        profile = VoiceProfile(
            name="Needs model",
            provider="qwen-character",
            voice_id="Ryan",
            model_id="custom-1.7b",
            qwen_mode="custom",
            qwen_profile_id="d3-model-report",
        )
        self.export([profile])
        plan = plan_qwen_profiles_import(self.bundle)
        compatibility = plan["profiles"][0]["compatibility"]
        self.assertFalse(compatibility["model_roles_ready"])
        self.assertFalse(compatibility["runtime_ready"])
        self.assertEqual(compatibility["destination_backend_preference"], "automatic")
        result = import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(result.imported_profile_ids, ("d3-model-report",))
        self.assertEqual(self.catalogue()[0]["backend"], "automatic")

    def test_clone_reference_and_original_sidecar_are_copied_byte_for_byte(self):
        source_dir = self.root / "source" / "Clone Hero"
        normalized = source_dir / "reference.wav"
        normalized_bytes = write_wav(normalized)
        original = source_dir / "original-recording.mp3"
        original_bytes = b"original-clone-source-bytes-are-not-transcoded"
        original.write_bytes(original_bytes)
        profile = VoiceProfile(
            name="Clone Hero",
            provider="qwen-character",
            voice_id="Clone Hero",
            model_id="base-0.6b",
            language="English",
            qwen_mode="clone",
            sample_path=str(normalized),
            reference_text="The exact original transcript.",
            authorized=False,
            qwen_profile_id="d3-clone-identity",
        )
        self.export([profile])
        result = import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(result.imported_profile_ids, (profile.qwen_profile_id,))
        imported = self.catalogue()[0]
        imported_reference = Path(imported["sample_path"])
        self.assertEqual(imported_reference.read_bytes(), normalized_bytes)
        self.assertEqual(hashlib.sha256(imported_reference.read_bytes()).hexdigest(),
                         hashlib.sha256(normalized_bytes).hexdigest())
        self.assertEqual((imported_reference.parent / original.name).read_bytes(), original_bytes)
        self.assertFalse(imported["authorized"])
        self.assertEqual(imported["reference_text"], profile.reference_text)
        self.assertTrue(imported_reference.is_relative_to(self.voices))

        # The existing exporter must still discover the exact source sidecar
        # beside the imported normalized reference.
        roundtrip = self.root / "roundtrip.ryuvoice"
        export_qwen_profiles_bundle(
            [load_saved_profiles()[0]],
            roundtrip,
            source_model_preference="0.6b",
        )
        self.assertTrue(roundtrip.is_file())

    def test_explicit_voicedesign_anchor_is_restored_to_profile_owned_storage(self):
        anchor_source = self.root / "source-anchor.wav"
        anchor_bytes = write_wav(anchor_source)
        profile = VoiceProfile(
            name="Explicit Japanese Design",
            provider="qwen-character",
            voice_id="design-explicit",
            model_id="design-1.7b",
            language="Japanese",
            qwen_mode="design",
            qwen_prompt="A warm, expressive Japanese narrator.",
            qwen_seed=9021,
            qwen_anchor_text="これは保存された参照文です。",
            qwen_anchor_path=str(anchor_source),
            qwen_profile_id="d3-explicit-anchor",
        )
        self.export([profile])
        result = import_qwen_profiles_bundle(self.bundle)
        record = self.catalogue()[0]
        destination = Path(record["qwen_anchor_path"])
        self.assertEqual(destination.read_bytes(), anchor_bytes)
        self.assertTrue(destination.is_relative_to(self.voices))
        self.assertIsNone(record["sample_path"])
        self.assertEqual(record["qwen_profile_id"], profile.qwen_profile_id)

    def test_derived_voicedesign_anchor_uses_the_existing_worker_cache_path(self):
        from app.tts.qwen_profile_schema import qwen_design_anchor_cache_path

        profile = VoiceProfile(
            name="Derived Design",
            provider="qwen-character",
            voice_id="design-derived",
            model_id="design-1.7b",
            language="Japanese",
            qwen_mode="design",
            qwen_prompt="A gentle Japanese voice.",
            qwen_seed=101,
            qwen_anchor_text="保存された中立アンカーです。",
            qwen_profile_id="d3-derived-anchor",
        )
        from app.tts.expression import default_voice_design_anchor_text
        effective_text = profile.qwen_anchor_text or default_voice_design_anchor_text(profile.language)
        source_anchor = qwen_design_anchor_cache_path(
            self.runtimes,
            speaker=profile.voice_id,
            language=profile.language,
            instruct=profile.qwen_prompt,
            seed=profile.qwen_seed,
            anchor_text=effective_text,
            profile_id=profile.qwen_profile_id,
            style="neutral",
        )
        anchor_bytes = write_wav(source_anchor)
        self.export([profile])
        result = import_qwen_profiles_bundle(self.bundle)
        imported = self.catalogue()[0]
        self.assertIsNone(imported["qwen_anchor_path"])
        destination = qwen_design_anchor_cache_path(
            self.runtimes,
            speaker=profile.voice_id,
            language=profile.language,
            instruct=profile.qwen_prompt,
            seed=profile.qwen_seed,
            anchor_text=effective_text,
            profile_id=profile.qwen_profile_id,
            style="neutral",
        )
        self.assertEqual(destination.read_bytes(), anchor_bytes)
        self.assertEqual(result.imported_profile_ids, (profile.qwen_profile_id,))

    def test_missing_voicedesign_anchor_requires_explicit_acknowledgement(self):
        profile = VoiceProfile(
            name="Design without cache",
            provider="qwen-character",
            voice_id="design-no-cache",
            model_id="design-1.7b",
            language="English",
            qwen_mode="design",
            qwen_prompt="A clear, natural narrator.",
            qwen_profile_id="d3-design-no-cache",
        )
        self.export([profile])
        plan = plan_qwen_profiles_import(self.bundle)
        self.assertTrue(plan["profiles"][0]["missing_voice_design_anchor_acknowledgement"])
        with self.assertRaises(QwenProfileImportConflict):
            import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(self.catalogue(), [])
        result = import_qwen_profiles_bundle(
            self.bundle,
            allow_missing_voicedesign_anchor=True,
        )
        self.assertEqual(result.imported_profile_ids, (profile.qwen_profile_id,))
        self.assertTrue(any("without a cached VoiceDesign anchor" in item for item in result.warnings))

    def test_same_profile_id_and_same_revision_is_idempotently_skipped(self):
        profile = VoiceProfile(
            name="Already imported",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_profile_id="d3-already-imported",
        )
        self.export([profile])
        first = import_qwen_profiles_bundle(self.bundle)
        second = import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(first.imported_profile_ids, (profile.qwen_profile_id,))
        self.assertEqual(second.imported_profile_ids, ())
        self.assertEqual(second.skipped_profile_ids, (profile.qwen_profile_id,))
        self.assertEqual(len(self.catalogue()), 1)

    def test_same_id_different_revision_defaults_to_recoverable_keep_both(self):
        original = VoiceProfile(
            name="Revisioned voice",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_prompt="First prompt.",
            qwen_profile_id="d3-revision-conflict",
        )
        self.export([original])
        import_qwen_profiles_bundle(self.bundle)
        changed = dict(self.catalogue()[0])
        changed["qwen_prompt"] = "Current destination prompt."
        self.save_catalogue([changed])

        incoming = VoiceProfile(
            name=original.name,
            provider=original.provider,
            voice_id=original.voice_id,
            qwen_mode="custom",
            qwen_prompt="Incoming older prompt.",
            qwen_profile_id=original.qwen_profile_id,
        )
        self.export([incoming])
        plan = plan_qwen_profiles_import(self.bundle)
        self.assertEqual(plan["profiles"][0]["classification"], "revision_conflict")
        result = import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(result.imported_profile_ids, ())
        self.assertEqual(len(result.stored_revision_ids), 1)
        self.assertEqual(self.catalogue()[0]["qwen_prompt"], "Current destination prompt.")
        revision_dir = self.voices / "Qwen Profile Revisions" / original.qwen_profile_id
        self.assertTrue(any(revision_dir.glob("*.json")))

    def test_explicit_replace_backs_up_previous_revision_before_switching_current(self):
        original = VoiceProfile(
            name="Replaceable voice",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_prompt="Original prompt.",
            qwen_profile_id="d3-replace-profile",
        )
        self.export([original])
        import_qwen_profiles_bundle(self.bundle)
        incoming = VoiceProfile(
            name=original.name,
            provider=original.provider,
            voice_id=original.voice_id,
            qwen_mode="custom",
            qwen_prompt="Replacement prompt.",
            qwen_profile_id=original.qwen_profile_id,
        )
        self.export([incoming])
        before = self.catalogue()[0]
        result = import_qwen_profiles_bundle(
            self.bundle,
            resolutions={original.qwen_profile_id: {"action": "replace"}},
        )
        after = self.catalogue()[0]
        self.assertEqual(after["qwen_prompt"], "Replacement prompt.")
        self.assertIn(original.qwen_profile_id, result.imported_profile_ids)
        self.assertTrue(
            list((self.voices / "Qwen Profile Revisions" / original.qwen_profile_id).glob("*.ryuvoice"))
        )
        self.assertNotEqual(before["qwen_prompt"], after["qwen_prompt"])

    def test_same_name_different_id_requires_explicit_new_name(self):
        existing = VoiceProfile(
            name="Shared name",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_profile_id="d3-existing-name",
        )
        self.save_catalogue([profile_record(existing)])
        incoming = VoiceProfile(
            name="Shared name",
            provider="qwen-character",
            voice_id="Serena",
            qwen_mode="custom",
            qwen_profile_id="d3-import-name",
        )
        self.export([incoming])
        plan = plan_qwen_profiles_import(self.bundle)
        self.assertEqual(plan["profiles"][0]["classification"], "name_collision")
        with self.assertRaises(QwenProfileImportConflict):
            import_qwen_profiles_bundle(self.bundle)
        result = import_qwen_profiles_bundle(
            self.bundle,
            resolutions={
                incoming.qwen_profile_id: {
                    "action": "keep_both",
                    "new_name": "Shared name • Imported",
                }
            },
        )
        self.assertEqual(result.renamed_profiles[incoming.qwen_profile_id], "Shared name • Imported")
        records = self.catalogue()
        self.assertEqual({item["name"] for item in records},
                         {"Shared name", "Shared name • Imported"})

    def test_duplicate_payload_with_different_id_is_reported_and_requires_decision(self):
        first = VoiceProfile(
            name="Semantic duplicate",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_prompt="Same voice.",
            qwen_profile_id="d3-semantic-a",
        )
        self.save_catalogue([profile_record(first)])
        second = VoiceProfile(
            name="Semantic duplicate",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_prompt="Same voice.",
            qwen_profile_id="d3-semantic-b",
        )
        self.export([second])
        plan = plan_qwen_profiles_import(self.bundle)
        self.assertEqual(plan["profiles"][0]["classification"], "semantic_duplicate")
        with self.assertRaises(QwenProfileImportConflict):
            import_qwen_profiles_bundle(self.bundle)
        result = import_qwen_profiles_bundle(
            self.bundle,
            resolutions={
                second.qwen_profile_id: {
                    "action": "keep_both",
                    "new_name": "Semantic duplicate • Imported",
                }
            },
        )
        self.assertEqual(result.imported_profile_ids, (second.qwen_profile_id,))

    def test_asset_failure_rolls_back_all_profiles_in_multi_profile_bundle(self):
        reference = self.root / "source" / "reference.wav"
        write_wav(reference)
        profiles = [
            VoiceProfile(
                name="First in selection",
                provider="qwen-character",
                voice_id="Ryan",
                qwen_mode="custom",
                qwen_profile_id="d3-multi-first",
            ),
            VoiceProfile(
                name="Second in selection",
                provider="qwen-character",
                voice_id="Clone",
                qwen_mode="clone",
                sample_path=str(reference),
                qwen_profile_id="d3-multi-second",
            ),
        ]
        self.export(profiles)
        with self.assertRaises(QwenProfileImportError):
            import_qwen_profiles_bundle(self.bundle, _fail_after_asset_writes=1)
        self.assertEqual(self.catalogue(), [])
        asset_root = self.voices / "Qwen Profile Assets"
        self.assertFalse(asset_root.exists() and any(asset_root.rglob("*.wav")))

    def test_failure_after_catalogue_replace_restores_original_catalogue_and_assets(self):
        reference = self.root / "source" / "reference.wav"
        write_wav(reference)
        profile = VoiceProfile(
            name="Rollback voice",
            provider="qwen-character",
            voice_id="Clone",
            qwen_mode="clone",
            sample_path=str(reference),
            qwen_profile_id="d3-rollback-profile",
        )
        self.export([profile])
        original = [
            {
                "name": "Unrelated saved profile",
                "provider": "qwen-character",
                "voice_id": "Ono_Anna",
                "qwen_mode": "custom",
                "qwen_profile_id": "d3-unrelated-profile",
            }
        ]
        self.save_catalogue(original)
        with self.assertRaises(QwenProfileImportError):
            import_qwen_profiles_bundle(
                self.bundle,
                _fail_after_catalogue_commit=True,
            )
        self.assertEqual(self.catalogue(), original)
        self.assertFalse(
            any((self.voices / "Qwen Profile Assets").rglob("*.wav"))
            if (self.voices / "Qwen Profile Assets").exists()
            else False
        )

    def test_interrupted_transaction_is_recovered_before_catalogue_load(self):
        original = [{"name": "Before", "provider": "qwen-character", "voice_id": "Ryan",
                     "qwen_mode": "custom", "qwen_profile_id": "d3-before"}]
        self.save_catalogue(original)
        transaction_id = "interrupted-test"
        transaction_dir = self.voices / ".qwen-profile-import-transactions" / transaction_id
        transaction_dir.mkdir(parents=True)
        (transaction_dir / "catalogue.before.json").write_text(
            json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        created = self.voices / "Qwen Profile Assets" / "partial.bin"
        created.parent.mkdir(parents=True)
        created.write_bytes(b"partial import")
        self.save_catalogue([{"name": "Partial", "provider": "qwen-character",
                              "voice_id": "Serena", "qwen_mode": "custom",
                              "qwen_profile_id": "d3-partial"}])
        (transaction_dir / "journal.json").write_text(
            json.dumps({
                "state": "catalogue_committed",
                "catalogue_existed": True,
                "created_paths": [str(created)],
            }),
            encoding="utf-8",
        )
        loaded = load_saved_profiles()
        self.assertEqual([item.name for item in loaded], ["Before"])
        self.assertFalse(created.exists())
        self.assertFalse(transaction_dir.exists())

    def test_corrupt_bundle_is_rejected_before_any_catalogue_mutation(self):
        profile = VoiceProfile(
            name="Corrupt input",
            provider="qwen-character",
            voice_id="Ryan",
            qwen_mode="custom",
            qwen_profile_id="d3-corrupt-input",
        )
        self.export([profile])
        corrupt = self.root / "corrupt.ryuvoice"
        corrupt.write_bytes(b"not a zip archive")
        before = self.catalogue()
        with self.assertRaises(ValueError):
            import_qwen_profiles_bundle(corrupt)
        self.assertEqual(self.catalogue(), before)
        self.assertEqual(list(self.voices.glob(".qwen-profile-import-transactions/*")), [])

    def test_existing_different_asset_bytes_are_never_overwritten(self):
        reference = self.root / "source" / "reference.wav"
        write_wav(reference)
        profile = VoiceProfile(
            name="No overwrite",
            provider="qwen-character",
            voice_id="Clone",
            qwen_mode="clone",
            sample_path=str(reference),
            qwen_profile_id="d3-no-overwrite",
        )
        self.export([profile])
        expected = import_qwen_profiles_bundle(self.bundle)
        record = self.catalogue()[0]
        imported_path = Path(record["sample_path"])
        original_bytes = imported_path.read_bytes()
        imported_path.write_bytes(b"changed bytes at the destination")
        self.save_catalogue([])
        with self.assertRaises(QwenProfileImportError):
            import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(imported_path.read_bytes(), b"changed bytes at the destination")
        self.assertEqual(self.catalogue(), [])

    def test_destination_backend_setting_is_not_changed_by_import(self):
        profile = VoiceProfile(
            name="Keep destination backend",
            provider="qwen-character",
            voice_id="Ryan",
            backend="cpu",
            qwen_mode="custom",
            qwen_profile_id="d3-backend-preserved",
        )
        self.export([profile])
        import_qwen_profiles_bundle(self.bundle)
        self.assertEqual(self.catalogue()[0]["backend"], "cpu")


if __name__ == "__main__":
    unittest.main()
