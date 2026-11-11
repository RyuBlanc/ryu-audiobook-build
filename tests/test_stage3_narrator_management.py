import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.ui.premium_v2_host import PremiumV2Bridge


class Stage3NarratorManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name)
        self.bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
        self.project = SimpleNamespace(
            title="Book One",
            folder=Path(self.temp.name) / "project",
        )
        self.state = {}

    def _write_series_default(self, name="Series Voice"):
        digest = hashlib.sha256("the series".encode("utf-8")).hexdigest()[:16]
        path = self.settings / "series-narrators" / f"the-series-{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": 1,
            "series": "The Series",
            "profile_name": name,
            "provider": "piper",
            "voice_id": name.lower().replace(" ", "-"),
            "updated_at": "2026-11-01T00:00:00Z",
        }), encoding="utf-8")
        return path

    def _profile(self, name):
        return SimpleNamespace(
            name=name, provider="piper", voice_id="voice-id", backend="automatic"
        )

    def test_inherited_project_uses_current_series_default_not_stale_snapshot(self):
        self._write_series_default("Series Voice V2")
        self.state = {
            "series": "The Series",
            "voice_profile": "Series Voice V1",
            "narrator_profile_source": "series_default",
        }
        self.bridge._find_profile = lambda name: self._profile(name) if name == "Series Voice V2" else None
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertEqual(result["effective_profile_name"], "Series Voice V2")
        self.assertIsNone(result["project_profile_name"])
        self.assertEqual(result["source"], "series_default")
        self.assertTrue(result["profile_available"])

    def test_series_default_change_propagates_only_to_inheriting_projects_after_restart(self):
        self._write_series_default("Series Voice V1")
        old_profile = self._profile("Series Voice V1")
        new_profile = self._profile("Series Voice V2")
        other_profile = self._profile("Other Series Voice")
        profiles = {
            old_profile.name: old_profile,
            new_profile.name: new_profile,
            other_profile.name: other_profile,
        }
        self.bridge._find_profile = lambda name: profiles.get(name)
        inherited_project_state = {
            "series": "The Series",
            "voice_profile": "Series Voice V1",
            "narrator_profile_source": "series_default",
        }
        override_project_state = {
            "series": "The Series",
            "voice_profile": "Book Override",
            "narrator_profile_source": "project_override",
        }

        with patch("app.core.paths.settings_root", return_value=self.settings):
            other_path = self.bridge._narrator_series_default_store_path("Other Series")
            other_path.parent.mkdir(parents=True, exist_ok=True)
            other_path.write_text(json.dumps({
                "schema_version": 1,
                "series": "Other Series",
                "profile_name": other_profile.name,
                "provider": "piper",
                "voice_id": other_profile.voice_id,
            }), encoding="utf-8")
            updated = self.bridge._narrator_series_default_save({
                "series": "The Series",
                "profile_name": new_profile.name,
            })
            # A fresh bridge represents a process/application restart: effective
            # narrator selection is re-read from persistent storage, not memory.
            reopened_bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            reopened_bridge._find_profile = lambda name: profiles.get(name)
            inherited_after = reopened_bridge._narrator_series_default_read(
                None, inherited_project_state, "The Series"
            )
            override_after = reopened_bridge._narrator_series_default_read(
                None, override_project_state, "The Series"
            )
            other_after = reopened_bridge._narrator_series_default_read(
                None,
                {"series": "Other Series", "narrator_profile_source": "series_default"},
                "Other Series",
            )

        self.assertTrue(updated["saved"])
        self.assertEqual(inherited_after["effective_profile_name"], "Series Voice V2")
        self.assertEqual(inherited_after["source"], "series_default")
        self.assertEqual(override_after["effective_profile_name"], "Book Override")
        self.assertEqual(override_after["source"], "project_override")
        self.assertEqual(other_after["effective_profile_name"], "Other Series Voice")
        self.assertEqual(other_after["series"], "Other Series")

    def test_explicit_project_override_wins_over_series_default(self):
        self._write_series_default("Series Voice")
        self.state = {
            "series": "The Series",
            "voice_profile": "Book Voice",
            "narrator_profile_source": "project_override",
        }
        self.bridge._find_profile = lambda name: self._profile(name)
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertEqual(result["effective_profile_name"], "Book Voice")
        self.assertEqual(result["project_profile_name"], "Book Voice")
        self.assertEqual(result["source"], "project_override")

    def test_legacy_project_profile_remains_an_override(self):
        self._write_series_default("Series Voice")
        self.state = {"series": "The Series", "voice_profile": "Legacy Book Voice"}
        self.bridge._find_profile = lambda name: self._profile(name)
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertEqual(result["effective_profile_name"], "Legacy Book Voice")
        self.assertEqual(result["source"], "project_override")

    def test_missing_default_does_not_fall_back_to_inherited_snapshot(self):
        self.state = {
            "series": "The Series",
            "voice_profile": "Deleted Old Series Voice",
            "narrator_profile_source": "series_default",
        }
        self.bridge._find_profile = lambda _name: None
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertIsNone(result["effective_profile_name"])
        self.assertEqual(result["source"], "none")
        self.assertFalse(result["profile_available"])

    def test_profile_rename_migrates_saved_series_narrator_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            defaults = root / "series-narrators"
            defaults.mkdir()
            path = defaults / "series-123.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "series": "The Series",
                "profile_name": "Old Narrator",
                "provider": "piper",
                "voice_id": "old-id",
                "updated_at": "2026-10-31T00:00:00Z",
            }), encoding="utf-8")
            previous = SimpleNamespace(name="Old Narrator", voice_id="old-id")
            updated = SimpleNamespace(name="New Narrator", voice_id="new-id", provider="kokoro", backend="automatic")
            with patch("app.ui.premium_v2_host.settings_root", return_value=root):
                with patch("app.ui.premium_v2_host.list_projects", return_value=[]):
                    with patch("app.ui.premium_v2_host.list_reusable_characters", return_value=[]):
                        self.bridge._migrate_saved_voice_profile_references(previous, updated, [previous, updated])
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["profile_name"], "New Narrator")
        self.assertEqual(record["provider"], "kokoro")
        self.assertEqual(record["voice_id"], "new-id")

    def test_character_voice_assignment_series_resolves_series_scope_and_explicit_identity(self):
        resolve = PremiumV2Bridge._character_series_for_voice_assignment
        self.assertEqual(
            resolve({"scope": "Series · The Series"}, "Book Series"),
            "The Series",
        )
        self.assertEqual(
            resolve({"scope": "Series: Another Series"}, "Book Series"),
            "Another Series",
        )
        self.assertEqual(
            resolve({"series": "Explicit Series", "scope": "Series · Other Series"}, "Book Series"),
            "Explicit Series",
        )
        self.assertEqual(
            resolve({"scope": "Current book only"}, "Book Series"),
            "Book Series",
        )

    def test_profile_delete_allows_stale_snapshot_when_project_inherits_new_series_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            defaults = root / "series-narrators"
            defaults.mkdir()
            (defaults / "series-123.json").write_text(json.dumps({
                "series": "The Series",
                "profile_name": "New Series Voice",
                "provider": "piper",
                "voice_id": "new-series-id",
            }), encoding="utf-8")
            project = SimpleNamespace(title="Book One", folder=root / "project")
            old_profile = self._profile("Old Series Voice")
            with patch("app.tts.voice_profile.load_saved_profiles", return_value=[old_profile]):
                with patch("app.tts.voice_profile.save_profiles") as save_profiles:
                    with patch("app.ui.premium_v2_host.settings_root", return_value=root):
                        with patch("app.ui.premium_v2_host.list_projects", return_value=[project]):
                            with patch("app.ui.premium_v2_host.load_state", return_value={
                                "voice_profile": "Old Series Voice",
                                "narrator_profile_source": "series_default",
                            }):
                                result = self.bridge._voice_delete({"profile_name": "Old Series Voice"})
            self.assertTrue(result["deleted"])
            save_profiles.assert_called_once_with([])

    def test_profile_delete_is_blocked_while_used_as_a_series_narrator_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            defaults = root / "series-narrators"
            defaults.mkdir()
            (defaults / "series-123.json").write_text(json.dumps({
                "series": "The Series",
                "profile_name": "Series Narrator",
                "provider": "piper",
                "voice_id": "series-voice",
            }), encoding="utf-8")
            saved_profile = SimpleNamespace(name="Series Narrator")
            with patch("app.tts.voice_profile.load_saved_profiles", return_value=[saved_profile]):
                with patch("app.tts.voice_profile.save_profiles") as save_profiles:
                    with patch("app.ui.premium_v2_host.settings_root", return_value=root):
                        with patch("app.ui.premium_v2_host.list_projects", return_value=[]):
                            with self.assertRaisesRegex(ValueError, "saved narrator default for series 'The Series'"):
                                self.bridge._voice_delete({"profile_name": "Series Narrator"})
            save_profiles.assert_not_called()

    def test_generation_uses_effective_series_narrator_not_transient_request_profile(self):
        chapter = Chapter(1, "One", "The sun rose over the quiet valley.")
        project = SimpleNamespace(chapters=[chapter])
        selection = {
            "effective_profile_name": "Series Narrator",
            "profile_name": "Series Narrator",
            "source": "series_default",
            "profile_available": True,
        }
        narrator_profile = self._profile("Series Narrator")
        self.bridge._project_series_name = lambda _project, _state: "The Series"
        self.bridge._narrator_series_default_read = lambda *_args: selection
        self.bridge._find_profile = lambda name: narrator_profile if name == "Series Narrator" else None
        profile, resolved = self.bridge._resolve_narrator_for_generation(
            project, {"voice_profile": "Temporary Voice"}, [chapter]
        )
        self.assertIs(profile, narrator_profile)
        self.assertEqual(resolved["source"], "series_default")
        self.assertEqual(profile.name, "Series Narrator")

    def test_generation_blocks_unidentified_quoted_dialogue_when_character_voice_is_configured(self):
        chapter = Chapter(1, "One", 'The gate opened. “Who are you?” Then silence followed.')
        project = SimpleNamespace(chapters=[chapter])
        self.bridge._project_series_name = lambda _project, _state: "The Series"
        self.bridge._narrator_series_default_read = lambda *_args: {
            "effective_profile_name": "Series Narrator",
            "profile_name": "Series Narrator",
            "source": "series_default",
            "profile_available": True,
        }
        narrator_profile = self._profile("Series Narrator")
        unassigned_profile = self._profile("Unassigned Character")
        profiles = {
            narrator_profile.name: narrator_profile,
            "Mira Voice": self._profile("Mira Voice"),
            unassigned_profile.name: unassigned_profile,
        }
        self.bridge._find_profile = lambda name: profiles.get(name)
        self.bridge._unassigned_character_default_read = lambda: {
            "profile_name": unassigned_profile.name,
            "profile_available": True,
            "profile": unassigned_profile,
        }
        # Unidentified quoted passages are accepted only when the mandatory
        # app-wide fallback exists; they remain visible as pending and route to
        # that voice instead of silently being assigned to the narrator.
        state = {"characters": [{"name": "Mira", "voice_profile": "Mira Voice"}]}
        with patch(
            "app.ui.premium_v2_host.load_profiles",
            return_value=list(profiles.values()),
        ):
            _profile, resolved = self.bridge._resolve_narrator_for_generation(project, state, [chapter])
        self.assertEqual(resolved["dialogue_routing"], "saved_character_assignments_with_unassigned_fallback")
        self.assertEqual(resolved["unassigned_character_profile_name"], unassigned_profile.name)
        self.assertGreaterEqual(resolved["pending_dialogue_count"], 1)

    def test_generation_fails_closed_when_effective_narrator_profile_is_missing(self):
        chapter = Chapter(1, "One", "The sun rose.")
        project = SimpleNamespace(chapters=[chapter])
        self.bridge._project_series_name = lambda _project, _state: "The Series"
        self.bridge._narrator_series_default_read = lambda *_args: {
            "effective_profile_name": "Deleted Narrator",
            "profile_name": "Deleted Narrator",
            "source": "series_default",
            "profile_available": False,
        }
        self.bridge._find_profile = lambda _name: None
        with self.assertRaisesRegex(ValueError, "effective narrator profile.*unavailable"):
            self.bridge._resolve_narrator_for_generation(project, {}, [chapter])

    def test_narrator_preview_uses_effective_profile_for_selected_narration_only(self):
        text = 'The sun rose. “Hello there.” Then the road was quiet.'
        first = text.index("The sun rose.")
        first_end = first + len("The sun rose.")
        chapter = Chapter(1, "One", text)
        self.project.chapters = [chapter]
        self.bridge._active_project = lambda: self.project
        self.bridge._project_series_name = lambda _project, _state: "The Series"
        self.bridge._narrator_series_default_read = lambda *_args: {
            "effective_profile_name": "Series Narrator",
            "profile_available": True,
            "source": "series_default",
        }
        self.bridge._voice_preview = lambda payload: {"job_id": "preview-1", "payload": payload}
        with patch("app.ui.premium_v2_host.load_state", return_value={"series": "The Series"}):
            result = self.bridge._narrator_preview({
                "chapter_number": 1,
                "start": first,
                "end": first_end,
                "text": text[first:first_end],
                "duration_seconds": 30,
            })
        self.assertEqual(result["job_id"], "preview-1")
        self.assertEqual(result["payload"]["profile_name"], "Series Narrator")
        self.assertEqual(result["payload"]["text"], "The sun rose.")
        self.assertFalse(result["payload"]["route_character_cast"])

    def test_narrator_preview_rejects_unidentified_quoted_dialogue(self):
        text = 'The sun rose. “Hello there.” Then the road was quiet.'
        start = text.index("“Hello there.”")
        end = start + len("“Hello there.”")
        chapter = Chapter(1, "One", text)
        self.project.chapters = [chapter]
        self.bridge._active_project = lambda: self.project
        self.bridge._voice_preview = lambda _payload: self.fail("Dialogue must not be synthesized as narration.")
        with patch("app.ui.premium_v2_host.load_state", return_value={"series": "The Series"}):
            with self.assertRaisesRegex(ValueError, "Narrator Preview accepts narration only"):
                self.bridge._narrator_preview({
                    "chapter_number": 1, "start": start, "end": end,
                    "text": text[start:end], "duration_seconds": 30,
                })

    def test_series_setup_preview_queues_real_voice_preview_worker_without_active_project(self):
        profile = self._profile("Series Narrator")
        self.bridge._assert_no_active_model_lifecycle = lambda _action: None
        self.bridge._assert_no_active_audio_synthesis = lambda _action: None

        def no_active_project():
            raise ValueError("Open a local project from the Library first.")

        self.bridge._active_project = no_active_project
        self.bridge._new_job = lambda *_args: "series-preview-job"
        self.bridge._job_update = lambda job_id, **changes: {"job_id": job_id, **changes}
        self.bridge._jobs_lock = threading.RLock()
        self.bridge._preview_cancel_events = {}

        with patch.object(PremiumV2Bridge, "_preview_profile_from_payload", return_value=profile):
            with patch("app.ui.premium_v2_host.threading.Thread") as thread_class:
                result = self.bridge._voice_preview({
                    "allow_projectless_preview": True,
                    "profile_name": profile.name,
                    "text": "Long ago, the journey began.",
                    "duration_seconds": 10,
                    "route_character_cast": False,
                })

        self.assertEqual(result["job_id"], "series-preview-job")
        self.assertEqual(result["profile_name"], "Series Narrator")
        self.assertEqual(result["duration_seconds"], 10)
        thread_class.assert_called_once()
        args = thread_class.call_args.kwargs["args"]
        self.assertEqual(args[0], "series-preview-job")
        self.assertIs(args[1], profile)
        self.assertEqual(args[2], "Long ago, the journey began.")
        self.assertEqual(args[3], 10)
        self.assertEqual(args[4], {})
        self.assertFalse(args[6])
        thread_class.return_value.start.assert_called_once()

    def test_series_setup_narrator_preview_uses_selected_saved_voice_without_project(self):
        profile = self._profile("Series Narrator")
        self.bridge._find_profile = lambda name: profile if name == profile.name else None
        self.bridge._voice_preview = lambda payload: payload
        result = self.bridge._narrator_preview({
            "series_setup_preview": True,
            "profile_name": profile.name,
            "text": "Long ago, a new journey began.",
            "duration_seconds": 10,
        })
        self.assertEqual(result["profile_name"], "Series Narrator")
        self.assertEqual(result["text"], "Long ago, a new journey began.")
        self.assertTrue(result["allow_projectless_preview"])
        self.assertFalse(result["route_character_cast"])

    def test_series_narrator_default_can_be_saved_for_a_new_series_without_active_project(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "series-default.json"
            profile = self._profile("Series Narrator")
            self.bridge._active_project = lambda: self.fail("Explicit series save must not require an active book.")
            self.bridge._find_profile = lambda name: profile if name == profile.name else None
            self.bridge._narrator_series_default_store_path = lambda _series: path
            self.bridge._now = lambda: "2026-11-01T00:00:00Z"
            result = self.bridge._narrator_series_default_save({
                "series": "New Series",
                "profile_name": profile.name,
            })
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(result["saved"])
        self.assertEqual(result["series"], "New Series")
        self.assertEqual(record["profile_name"], "Series Narrator")

    def test_reset_restores_series_inheritance_and_clears_project_snapshot(self):
        self._write_series_default("Series Voice")
        self.state = {
            "series": "The Series",
            "voice_profile": "Book Override",
            "voice_id": "book-id",
            "backend": "piper",
            "narrator": "Book Override",
            "narrator_profile_source": "project_override",
        }
        self.bridge._active_project = lambda: self.project
        self.bridge._find_profile = lambda name: self._profile(name) if name == "Series Voice" else None
        with patch("app.ui.premium_v2_host.load_state", return_value=self.state):
            with patch("app.ui.premium_v2_host.save_state") as save:
                with patch("app.core.paths.settings_root", return_value=self.settings):
                    result = self.bridge._narrator_project_reset({"series": "The Series"})
        self.assertNotIn("voice_profile", self.state)
        self.assertNotIn("voice_id", self.state)
        self.assertEqual(self.state["narrator_profile_source"], "series_default")
        self.assertEqual(self.state["narrator"], "Series Voice")
        self.assertEqual(result["profile_name"], "Series Voice")
        self.assertEqual(result["source"], "series_default")
        save.assert_called_once_with(self.project.folder, self.state)


if __name__ == "__main__":
    unittest.main()
