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
        with self.assertRaisesRegex(ValueError, "Unsupported audio format"):
            library.validate_saved_audio_paths({"ending_cue_path": str(unsupported)})
        broken = self.root / "broken.mp3"; broken.write_bytes(b"not mp3")
        with self.assertRaisesRegex(ValueError, "unreadable|duration"):
            library.validate_saved_audio_paths({"ambience_audio_path": str(broken)})

    def test_chapter_bgm_assignment_edit_clear_and_reload_are_project_isolated(self):
        track = _valid_wav(self.app_root / "Audio Library" / "track.wav")
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "track"}]
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
        self.bridge_a.catalog = [{"path": str(track.resolve()), "title": "opening"}]
        self.assertTrue(host.PremiumV2Bridge._sound_cues_save(self.bridge_a, {"slot": "opening", "path": str(track)})["saved"])
        self.assertEqual(host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})["opening"]["path"], str(track.resolve()))
        self.assertIsNone(host.PremiumV2Bridge._sound_cues_get(self.bridge_b, {})["opening"]["path"])
        host.PremiumV2Bridge._sound_cues_clear(self.bridge_a, {})
        self.assertIsNone(host.PremiumV2Bridge._sound_cues_get(self.bridge_a, {})["opening"]["path"])

    def test_catalogue_uses_sidecar_title_license_and_duration(self):
        track = _valid_wav(self.app_root / "Audio Library" / "custom.wav")
        track.with_name(track.name + ".license.json").write_text(json.dumps({
            "title": "A Custom Cue", "license_note": "CC0", "duration_seconds": 1.0}), encoding="utf-8")
        rows = host.PremiumV2Bridge._sound_catalog(self.bridge_a, {})
        row = next(item for item in rows if item["path"] == str(track.resolve()))
        self.assertEqual(row["title"], "A Custom Cue"); self.assertEqual(row["licensing"], "CC0")
        self.assertEqual(row["duration_seconds"], 1.0)

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
        self.assertEqual(state["background_audio_fade_out"], 5.0)
        self.assertFalse(disabled["enabled"])

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
        self.assertIn('opening_cue_path=Path(state["opening_cue_path"]) if book_cues_enabled and state.get("opening_cue_path") else None', generation)
        self.assertIn('opening_cue_path=Path(str(state["opening_cue_path"])) if book_cues_enabled and state.get("opening_cue_path") else None', preview_source)

if __name__ == "__main__": unittest.main()
