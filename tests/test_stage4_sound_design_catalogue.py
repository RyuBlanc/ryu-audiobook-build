"""Stage 4 real sound-design catalogue, persistence, and asset safety regressions."""
from __future__ import annotations
import json, tempfile, unittest, wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.audio import library, assembler
from app.ui import premium_v2_host as host

def _valid_wav(path: Path, seconds: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000 * seconds)
    return path

class _BridgeHarness:
    def __init__(self, folder, chapters=()):
        self.project = SimpleNamespace(folder=Path(folder), chapters=list(chapters))
    def _active_project(self): return self.project
    def _now(self): return "2026-10-22T00:00:00+00:00"
    def _sound_catalog(self, _payload): return getattr(self, "catalog", [])
    def _sound_chapter_bgm_get(self, payload): return host.PremiumV2Bridge._sound_chapter_bgm_get(self, payload)

class SoundDesignCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.app_root = self.root / "Ryu's Audiobook"; self.app_root.mkdir()
        self.project_a, self.project_b = self.root / "book-a", self.root / "book-b"
        self.project_a.mkdir(); self.project_b.mkdir()
        self.bridge_a = _BridgeHarness(self.project_a, [SimpleNamespace(number=1, title="One")])
        self.bridge_b = _BridgeHarness(self.project_b, [SimpleNamespace(number=1, title="Other")])
        self.app_patch = patch.object(host, "app_root", return_value=self.app_root)
        self.app_patch.start(); self.addCleanup(self.app_patch.stop)

    def test_library_import_copies_audio_and_persists_metadata_without_touching_source(self):
        source = _valid_wav(self.root / "original.wav"); original = source.read_bytes()
        with patch.object(library, "audio_library_root", return_value=self.app_root / "Audio Library"):
            imported = library.import_audio_files([source], target_kind="music", license_note="CC0")
        self.assertEqual(source.read_bytes(), original); self.assertEqual(len(imported), 1)
        metadata = json.loads(imported[0].with_name(imported[0].name + ".license.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["license_note"], "CC0"); self.assertTrue(imported[0].is_file())

    def test_library_import_rejects_missing_or_unsupported_assets(self):
        with patch.object(library, "audio_library_root", return_value=self.app_root / "Audio Library"):
            with self.assertRaisesRegex(ValueError, "Unsupported or missing audio asset"):
                library.import_audio_files([self.root / "absent.wav"], target_kind="music")
            unsupported = self.root / "bad.exe"; unsupported.write_bytes(b"not audio")
            with self.assertRaisesRegex(ValueError, "Unsupported or missing audio asset"):
                library.import_audio_files([unsupported], target_kind="music")

    def test_deleted_explicit_music_or_cue_never_falls_back_to_another_track(self):
        valid = _valid_wav(self.root / "fallback.wav")
        with patch.object(library, "list_music_tracks", return_value=[library.AudioTrack(valid, "universal", "Universal")]):
            with self.assertRaisesRegex(FileNotFoundError, "missing"):
                library.resolve_music_track("universal", selected_track=self.root / "deleted.wav")
        with patch.object(library, "list_cue_tracks", return_value=[valid]):
            with self.assertRaisesRegex(FileNotFoundError, "missing|no longer exists"):
                library.resolve_cue_track("opening", selected_path=self.root / "deleted.wav")

    def test_saved_path_validation_rejects_missing_unsupported_and_unreadable_files(self):
        with self.assertRaisesRegex(FileNotFoundError, "Reassign it in Sound Design"):
            library.validate_saved_audio_paths({"opening_cue_path": str(self.root / "deleted.wav")})
        unsupported = self.root / "cue.exe"; unsupported.write_bytes(b"fake")
        unsupported.with_name(unsupported.name + ".license.json").write_text(
            json.dumps({"role":"cue","category":"ending"}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "unsupported audio format"):
            library.validate_saved_audio_paths({"ending_cue_path": str(unsupported)})
        broken = self.root / "broken.mp3"; broken.write_bytes(b"not mp3")
        with self.assertRaisesRegex(ValueError, "unreadable|duration"):
            library.validate_saved_audio_paths({"ambience_audio_path": str(broken)})

    def test_chapter_bgm_assignment_edit_clear_and_reload_are_project_isolated(self):
        track = _valid_wav(self.app_root / "Audio Library" / "track.wav")
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "track"}]
        host.PremiumV2Bridge._sound_chapter_bgm_save(self.bridge_a, {"strategy": "custom"})
        saved = host.PremiumV2Bridge._sound_chapter_bgm_save(self.bridge_a, {
                "number": 1, "rule": "custom", "path": str(track), "volume": 0.2,
                "start_offset": "after_10_seconds", "end_behavior": "continue_to_transition"})
        self.assertTrue(saved["saved"])
        reloaded = host.PremiumV2Bridge._sound_chapter_bgm_get(self.bridge_a, {})
        self.assertEqual(reloaded["overrides"]["1"]["path"], str(track.resolve()))
        self.assertEqual(reloaded["overrides"]["1"]["end_behavior"], "continue_to_transition")
        host.PremiumV2Bridge._sound_chapter_bgm_save(self.bridge_a, {"number": 1, "rule": "none"})
        self.assertEqual(host.PremiumV2Bridge._sound_chapter_bgm_get(self.bridge_a, {})["overrides"]["1"]["rule"], "none")
        self.assertEqual(host.PremiumV2Bridge._sound_chapter_bgm_get(self.bridge_b, {})["overrides"], {})

    def test_cue_assignments_save_clear_and_reload_are_book_local(self):
        track = _valid_wav(self.app_root / "Audio Library" / "opening.wav")
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "opening", "role": "cue", "duration_seconds": 1.0}]
        self.assertTrue(host.PremiumV2Bridge._sound_cues_save(self.bridge_a, {"slot": "opening", "path": str(track)})["saved"])
        self.assertEqual(host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})["opening"]["path"], str(track.resolve()))
        self.assertIsNone(host.PremiumV2Bridge._sound_cues_get(self.bridge_b, {})["opening"]["path"])
        host.PremiumV2Bridge._sound_cues_clear(self.bridge_a, {})
        self.assertIsNone(host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})["opening"]["path"])


    def test_cue_assignments_rehydrate_from_sidecar_after_catalogue_refresh(self):
        track = _valid_wav(self.app_root / "Audio Library" / "restart-cue.wav", seconds=1)
        track.with_name(track.name + ".license.json").write_text(json.dumps({
            "role": "cue", "category": "universal", "title": "Restart cue",
        }), encoding="utf-8")
        from app.core.state import load_state, save_state
        state = load_state(self.project_a)
        state.update({
            "sound_cues": {
                "opening": str(track.resolve()),
                "chapter": str(track.resolve()),
                "closing": str(track.resolve()),
            },
            "opening_cue_path": str(track.resolve()),
            "page_turn_cue_path": str(track.resolve()),
            "ending_cue_path": str(track.resolve()),
        })
        save_state(self.project_a, state)

        # A new bridge instance must be able to hydrate the saved assignment
        # from its persisted sidecar even if its first catalogue snapshot is empty.
        restarted_bridge = _BridgeHarness(self.project_a, self.bridge_a.project.chapters)
        restarted_bridge.catalog = []
        restored = host.PremiumV2Bridge._sound_cues_get(restarted_bridge, {})
        for slot in ("opening", "chapter", "closing"):
            self.assertEqual(restored[slot]["path"], str(track.resolve()))
            self.assertTrue(restored[slot]["available"])
            self.assertTrue(restored[slot]["assigned"])
            self.assertFalse(restored[slot]["missing"])
            self.assertEqual(restored[slot]["title"], "Restart cue")

    def test_cue_rehydration_normalizes_catalogue_path_case(self):
        track = _valid_wav(self.app_root / "Audio Library" / "case-cue.wav", seconds=1)
        track.with_name(track.name + ".license.json").write_text(json.dumps({
            "role": "cue", "category": "universal", "title": "Case cue",
        }), encoding="utf-8")
        from app.core.state import load_state, save_state
        state = load_state(self.project_a)
        state["sound_cues"] = {
            "opening": str(track.resolve()), "chapter": None, "closing": None,
        }
        save_state(self.project_a, state)
        # Simulate a catalogue path with different casing after a new scan.
        self.bridge_a.catalog = [{
            "path": str(track.resolve()).swapcase(), "role": "cue", "title": "Case cue",
        }]
        restored = host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})
        self.assertEqual(restored["opening"]["path"], str(track.resolve()))
        self.assertTrue(restored["opening"]["available"])

    def test_cue_rehydration_preserves_missing_saved_path_for_relinking(self):
        missing_path = str((self.app_root / "Audio Library" / "removed-cue.wav").resolve())
        from app.core.state import load_state, save_state
        state = load_state(self.project_a)
        state["sound_cues"] = {"opening": missing_path, "chapter": None, "closing": None}
        save_state(self.project_a, state)
        self.bridge_a.catalog = []
        restored = host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})
        self.assertEqual(restored["opening"]["path"], missing_path)
        self.assertTrue(restored["opening"]["assigned"])
        self.assertFalse(restored["opening"]["available"])
        self.assertTrue(restored["opening"]["missing"])

    def test_cue_rehydration_reads_legacy_fields_when_canonical_slot_is_empty(self):
        track = _valid_wav(self.app_root / "Audio Library" / "legacy-cue.wav", seconds=1)
        track.with_name(track.name + ".license.json").write_text(json.dumps({
            "role": "cue", "category": "universal", "title": "Legacy cue",
        }), encoding="utf-8")
        from app.core.state import load_state, save_state
        state = load_state(self.project_a)
        state["sound_cues"] = {"opening": None, "chapter": None, "closing": None}
        state["opening_cue_path"] = str(track.resolve())
        save_state(self.project_a, state)
        self.bridge_a.catalog = []
        restored = host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})
        self.assertEqual(restored["opening"]["path"], str(track.resolve()))
        self.assertTrue(restored["opening"]["available"])


    def test_only_opening_next_chapter_and_closing_are_supported_fixed_cue_slots(self):
        for slot in ("scene", "transition", "unknown"):
            with self.assertRaisesRegex(ValueError, "Opening, Next Chapter, or Closing"):
                host.PremiumV2Bridge._sound_cues_save(self.bridge_a, {"slot": slot, "path": ""})

    def test_catalogue_uses_sidecar_title_license_and_duration(self):
        track = _valid_wav(self.app_root / "Audio Library" / "custom.wav")
        track.with_name(track.name + ".license.json").write_text(json.dumps({
            "title": "A Custom Cue", "license_note": "CC0", "duration_seconds": 1.0,
            "category": "fantasy"}), encoding="utf-8")
        rows = host.PremiumV2Bridge._sound_catalog(self.bridge_a, {})
        row = next(item for item in rows if item["path"] == str(track.resolve()))
        self.assertEqual(row["title"], "A Custom Cue"); self.assertEqual(row["licensing"], "CC0")
        self.assertEqual(row["duration_seconds"], 1.0)
        self.assertEqual(row["category"], "fantasy")

    def test_imported_music_category_roundtrips_into_catalogue(self):
        source = _valid_wav(self.root / "incoming-romance.wav")
        result = host.PremiumV2Bridge._sound_import(self.bridge_a, {
            "paths": [str(source)], "target_kind": "music",
            "category": "romance", "license_note": "CC0",
        })
        self.assertFalse(result["cancelled"])
        imported_path = Path(result["imported"][0]["path"])
        metadata = json.loads(imported_path.with_name(imported_path.name + ".license.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["category"], "romance")
        row = next(item for item in host.PremiumV2Bridge._sound_catalog(self.bridge_a, {}) if item["path"] == str(imported_path.resolve()))
        self.assertEqual(row["category"], "romance")

    def test_final_output_cannot_overwrite_selected_sound_asset(self):
        asset = _valid_wav(self.root / "source.m4b")
        chapter_dir = self.root / "chapter"; chapter_dir.mkdir()
        with patch.object(assembler, "assemble_chapter", return_value=chapter_dir / "chapter.m4a"):
            with self.assertRaisesRegex(ValueError, "overwrite"):
                assembler.assemble_m4b([chapter_dir], asset, "Test", "", None, [], background_audio_path=asset)

    def test_sound_manifest_persists_bounded_fades_and_zero_volume(self):
        track = Path(self.app_root) / "Audio Library" / "manifest.wav"
        _valid_wav(track)
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "manifest"}]
        saved = host.PremiumV2Bridge._sound_save_manifest(self.bridge_a, {
            "path": str(track), "enabled": True, "volume": 0.0,
            "fade_in_seconds": 0, "fade_out_seconds": 8})
        from app.core.state import load_state
        state = load_state(self.project_a)
        self.assertEqual(state["background_audio_volume"], 0.0)
        self.assertEqual(state["background_audio_fade_in"], 0.0)
        self.assertEqual(state["background_audio_fade_out"], 8.0)
        self.assertEqual(saved["fade_out_seconds"], 8.0)
        disabled = host.PremiumV2Bridge._sound_save_manifest(self.bridge_a, {
            "path": "", "enabled": False, "volume": 0.0,
            "fade_in_seconds": 0, "fade_out_seconds": 5})
        state = load_state(self.project_a)
        self.assertEqual(state["background_audio_mode"], "off")
        self.assertEqual(state["background_audio_path"], "")
        self.assertEqual(state["background_audio_preferred_path"], str(track.resolve()))
        self.assertEqual(state["background_audio_fade_out"], 5.0)
        self.assertFalse(disabled["enabled"])
        summary = host.PremiumV2Bridge._sound_chapter_bgm_get(self.bridge_a, {})
        self.assertFalse(summary["bgm_enabled"])
        self.assertEqual(summary["default_path"], str(track.resolve()))
        self.assertTrue(summary["default_available"])
        self.assertEqual(summary["last_saved_at"], "2026-10-22T00:00:00+00:00")


    def test_chapter_bgm_can_be_enabled_without_activating_book_default(self):
        track = _valid_wav(self.app_root / "Audio Library" / "chapter-only.wav")
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "chapter-only", "role": "music"}]
        host.PremiumV2Bridge._sound_chapter_bgm_save(self.bridge_a, {"strategy": "custom"})
        host.PremiumV2Bridge._sound_chapter_bgm_save(self.bridge_a, {
            "number": 1, "rule": "custom", "path": str(track), "volume": 0.2,
            "start_offset": "immediate", "end_behavior": "fade_before_end"
        })
        saved = host.PremiumV2Bridge._sound_save_manifest(self.bridge_a, {
            "path": "", "enabled": True, "volume": 0.18, "fade_in_seconds": 2, "fade_out_seconds": 3
        })
        from app.core.state import load_state
        state = load_state(self.project_a)
        self.assertTrue(state["background_audio_enabled"])
        self.assertEqual(state["background_audio_mode"], "manual")
        self.assertEqual(state["background_audio_path"], "")
        self.assertTrue(saved["enabled"])
        summary = host.PremiumV2Bridge._sound_chapter_bgm_get(self.bridge_a, {})
        self.assertTrue(summary["bgm_enabled"])
        self.assertEqual(summary["strategy"], "custom")
        self.assertEqual(summary["overrides"]["1"]["path"], str(track.resolve()))

    def test_cue_summary_distinguishes_unassigned_from_missing_file(self):
        track = _valid_wav(self.app_root / "Audio Library" / "vanishing-cue.wav")
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "vanishing-cue", "role": "cue"}]
        host.PremiumV2Bridge._sound_cues_save(self.bridge_a, {"slot": "opening", "path": str(track)})
        track.unlink()
        self.bridge_a.catalog = []
        missing = host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})["opening"]
        self.assertTrue(missing["assigned"])
        self.assertTrue(missing["missing"])
        self.assertFalse(missing["available"])
        self.assertEqual(missing["path"], str(track.resolve()))
        host.PremiumV2Bridge._sound_cues_clear(self.bridge_a, {})
        empty = host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})["opening"]
        self.assertFalse(empty["assigned"])
        self.assertFalse(empty["missing"])

    def test_production_generation_passes_saved_fades_and_preserves_zero_volumes(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = source.index("def _production_generate_book")
        end = source.index("def _generation_progress", start)
        generation = source[start:end]
        self.assertIn("background_audio_fade_in=float(state.get", generation)
        self.assertIn("background_audio_fade_out=float(state.get", generation)
        self.assertIn("background_audio_volume=float(state.get(\"background_audio_volume\") if state.get(\"background_audio_volume\") is not None else 0.18)", generation)
        adapter = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertNotIn("if ($('setBookDefaultTrack')) $('setBookDefaultTrack').onclick", adapter)
        self.assertNotIn("if ($('saveSoundPresetAdvanced')) $('saveSoundPresetAdvanced').onclick", adapter)
        self.assertIn("fade_in_seconds:fadeSeconds('bgmFadeIn')", adapter)
        self.assertIn("fade_out_seconds:fadeSeconds('bgmFadeOut')", adapter)

    def test_preview_and_production_do_not_mask_missing_saved_paths(self):
        host_source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        preview_source = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        self.assertIn("validate_saved_audio_paths(state)", host_source)
        self.assertIn("validate_saved_audio_paths(state)", preview_source)
        generation = host_source[host_source.index("def _production_generate_book"):host_source.index("def _sound_catalog")]
        self.assertIn('sound_enabled = background_audio_mode != "off"', generation)
        self.assertIn('chapter_transition_sound=effective_chapter_transition_sound,', generation)
        self.assertIn('opening_cue_path = (', generation)
        self.assertIn('Path(state["opening_cue_path"])\n            if effective_chapter_transition_sound and state.get("opening_cue_path") else None', generation)
        self.assertIn('page_turn_cue_path=page_turn_cue_path,', generation)
        self.assertIn('ending_cue_path=ending_cue_path,', generation)
        self.assertIn("chapter_transition_sound = sound_enabled and bool(state.get(\"chapter_transition_sound\", False))", preview_source)
        self.assertIn('opening_cue_path = (', preview_source)
        self.assertIn('Path(str(state["opening_cue_path"])) if chapter_transition_sound and state.get("opening_cue_path") else None', preview_source)
        self.assertIn('page_turn_cue_path=page_turn_cue_path,', preview_source)
        self.assertIn('ending_cue_path=ending_cue_path,', preview_source)


    def test_seeded_starter_tracks_are_built_in_and_not_duplicated(self):
        version = "starter-test-v1"
        audio_root = self.app_root / "Audio Library" / "music" / "fantasy"
        seeded = audio_root / "starter-theme.wav"
        _valid_wav(seeded)
        seeded.with_name(seeded.name + ".license.json").write_text(json.dumps({
            "role": "music", "category": "fantasy", "title": "Starter Theme",
            "original_filename": "starter-theme.wav", "starter_pack_version": version,
            "license_note": "CC0",
        }), encoding="utf-8")

        user_import = self.app_root / "Audio Library" / "music" / "romance" / "my-track.wav"
        _valid_wav(user_import)
        user_import.with_name(user_import.name + ".license.json").write_text(json.dumps({
            "role": "music", "category": "romance", "title": "My Imported Track",
            "original_filename": "my-track.wav", "license_note": "User import",
        }), encoding="utf-8")

        frozen_root = self.root / "frozen"
        bundle = frozen_root / "assets" / "starter_audio"
        bundled_seed = bundle / "music" / "fantasy" / "starter-theme.wav"
        _valid_wav(bundled_seed)
        bundled_only = bundle / "music" / "sci-fi" / "bundle-only.wav"
        _valid_wav(bundled_only)
        (bundle / "manifest.json").write_text(json.dumps({
            "version": version,
            "tracks": [
                {"type": "music", "category": "fantasy",
                 "bundle_path": "music/fantasy/starter-theme.wav", "title": "Starter Theme",
                 "license": "CC0", "license_note": "Starter"},
                {"type": "music", "category": "sci-fi",
                 "bundle_path": "music/sci-fi/bundle-only.wav", "title": "Bundle Only",
                 "license": "CC0", "license_note": "Starter"},
            ],
        }), encoding="utf-8")

        with patch.object(host.sys, "_MEIPASS", str(frozen_root), create=True):
            rows = host.PremiumV2Bridge._sound_catalog(self.bridge_a, {})

        starter_rows = [row for row in rows if row["title"] == "Starter Theme"]
        self.assertEqual(len(starter_rows), 1)
        self.assertEqual(starter_rows[0]["source"], "Bundled with application")
        self.assertEqual(Path(starter_rows[0]["path"]), seeded.resolve())
        imported = next(row for row in rows if row["title"] == "My Imported Track")
        self.assertEqual(imported["source"], "Imported locally")
        bundled_only_row = next(row for row in rows if row["title"] == "Bundle Only")
        self.assertEqual(bundled_only_row["source"], "Bundled with application")


    def test_roleless_assets_in_canonical_cue_folders_remain_cues(self):
        cue = _valid_wav(self.app_root / "Audio Library" / "cues" / "opening" / "legacy-opening.wav")
        rows = host.PremiumV2Bridge._sound_catalog(self.bridge_a, {})
        row = next(item for item in rows if item["path"] == str(cue.resolve()))
        self.assertEqual(row["role"], "cue")

    def test_corrupt_audio_sidecar_does_not_abort_the_rest_of_the_catalogue(self):
        corrupt = _valid_wav(self.app_root / "Audio Library" / "music" / "calm" / "bad-sidecar.wav")
        corrupt.with_name(corrupt.name + ".license.json").write_text("{not-json", encoding="utf-8")
        valid = _valid_wav(self.app_root / "Audio Library" / "music" / "romance" / "valid-track.wav")
        rows = host.PremiumV2Bridge._sound_catalog(self.bridge_a, {})
        paths = {row["path"] for row in rows}
        self.assertNotIn(str(corrupt.resolve()), paths)
        self.assertIn(str(valid.resolve()), paths)


    def test_level_only_manifest_update_preserves_saved_global_mode(self):
        track = _valid_wav(self.app_root / "Audio Library" / "preserved-mode.wav")
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "preserved-mode"}]
        from app.core.state import load_state, save_state

        volume_payload = {
            "path": "",
            "volume": 0.18,
            "narration_volume": 0.82,
            "cue_volume": 0.30,
            "fade_in_seconds": 2,
            "fade_out_seconds": 3,
        }
        # A volume-only manifest update must preserve Voice Only even when
        # music/cue preferences remain saved for later re-enabling.
        state = load_state(self.project_a)
        state.update({
            "background_audio_mode": "off",
            "background_audio_enabled": False,
            "background_audio_path": "",
            "background_audio_preferred_path": str(track.resolve()),
            "chapter_bgm_strategy": "custom",
            "chapter_bgm_overrides": {
                "1": {"rule": "custom", "path": str(track.resolve()), "volume": 0.18},
            },
        })
        save_state(self.project_a, state)
        disabled = host.PremiumV2Bridge._sound_save_manifest(self.bridge_a, volume_payload)
        state = load_state(self.project_a)
        self.assertEqual(state["background_audio_mode"], "off")
        self.assertFalse(state["background_audio_enabled"])
        self.assertEqual(state["background_audio_path"], "")
        self.assertEqual(state["background_audio_preferred_path"], str(track.resolve()))
        self.assertFalse(disabled["enabled"])

        # Chapter-Based BGM can be enabled without a book-default track. A
        # volume-only save must preserve that explicit enabled/manual mode.
        state.update({
            "background_audio_mode": "manual",
            "background_audio_enabled": True,
            "background_audio_path": "",
            "chapter_bgm_strategy": "custom",
            "chapter_bgm_overrides": {
                "1": {"rule": "custom", "path": str(track.resolve()), "volume": 0.18},
            },
        })
        save_state(self.project_a, state)
        enabled = host.PremiumV2Bridge._sound_save_manifest(self.bridge_a, volume_payload)
        state = load_state(self.project_a)
        self.assertEqual(state["background_audio_mode"], "manual")
        self.assertTrue(state["background_audio_enabled"])
        self.assertEqual(state["background_audio_path"], "")
        self.assertTrue(enabled["enabled"])

if __name__ == "__main__": unittest.main()
