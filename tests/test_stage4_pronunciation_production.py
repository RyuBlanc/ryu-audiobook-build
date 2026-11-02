"""Stage 4 Step 2.1: Production Generate must receive the effective pronunciation rules."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.ui import premium_v2_host as host


class ProductionPronunciationConnectivityTests(unittest.TestCase):
    def _start_production(self, root: Path, enabled: bool) -> list[dict]:
        project_folder = root / ("project-on" if enabled else "project-off")
        project_folder.mkdir(parents=True, exist_ok=True)
        output_root = root / "output"
        output_root.mkdir(parents=True, exist_ok=True)

        project = SimpleNamespace(
            folder=project_folder,
            title="Pronunciation Connectivity",
            chapters=[
                SimpleNamespace(
                    number=1,
                    title="Opening",
                    text="NYC meets Mira.",
                    skip_for_generation=False,
                )
            ],
        )
        profile = SimpleNamespace(name="Saved Narrator", voice_id="narrator-voice")
        manager = Mock()
        bridge = SimpleNamespace(
            _assert_no_active_model_lifecycle=Mock(),
            close_preview_provider_cache=Mock(),
            _active_project=Mock(return_value=project),
            _resolve_narrator_for_generation=Mock(
                return_value=(profile, {"source": "project_override", "profile_name": profile.name})
            ),
            _project_series_name=Mock(return_value="Slime"),
            _new_job=Mock(return_value="pronunciation-connectivity-job"),
            _now=Mock(return_value="2026-11-02T00:00:00+05:30"),
            _generation_progress=Mock(),
            _generation_finished=Mock(),
            _job_update=Mock(),
            _jobs_lock=threading.RLock(),
            _generators={},
            settings=SimpleNamespace(value=lambda _key, default=None: default),
        )
        state = {
            "author": "Saved Author",
            "language": "en",
            "genre": "Fantasy",
            "series": "Slime",
            "pronunciation_enabled": enabled,
            "pronunciation_dictionary": [
                {"written_form": "NYC", "spoken_form": "Book City", "enabled": True},
                {"written_form": "Disabled", "spoken_form": "Ignored", "enabled": False},
                {"written_form": "BookOnly", "spoken_form": "Book Reading", "enabled": True},
            ],
            "background_audio_mode": "off",
        }

        with patch.object(host, "load_state", return_value=state), \
             patch.object(host, "save_state"), \
             patch.object(host, "provider_from_profile", return_value=(object(), "narrator-voice")), \
             patch.object(host, "load_profiles", return_value=[]), \
             patch.object(host, "audiobooks_root", return_value=output_root), \
             patch.object(host, "GenerationManager", return_value=manager) as manager_factory:
            result = host.PremiumV2Bridge._production_generate_book(bridge, {})

        self.assertEqual(result["state"], "running")
        manager.start.assert_called_once()
        manager_factory.assert_called_once()
        return manager_factory.call_args.kwargs["pronunciation_dictionary"]

    def test_production_generate_receives_scoped_rules_and_global_off_bypasses_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = root / "settings"
            settings.mkdir()

            with patch.object(host, "settings_root", return_value=settings):
                host._write_pronunciation_store(
                    host._pronunciation_scope_path("series", "Slime"),
                    [
                        {"written_form": "NYC", "spoken_form": "Series City"},
                        {"written_form": "Mira", "spoken_form": "Series Mira"},
                        {"written_form": "SeriesOnly", "spoken_form": "Series Reading"},
                        {"written_form": "Disabled", "spoken_form": "Series Reading"},
                    ],
                )
                host._write_pronunciation_store(
                    host._pronunciation_scope_path("global_library"),
                    [
                        {"written_form": "NYC", "spoken_form": "Global City"},
                        {"written_form": "Mira", "spoken_form": "Global Mira"},
                        {"written_form": "GlobalOnly", "spoken_form": "Global Reading"},
                        {"written_form": "Disabled", "spoken_form": "Global Reading"},
                    ],
                )

                enabled_rules = self._start_production(root, enabled=True)
                disabled_rules = self._start_production(root, enabled=False)

        effective = {
            row["written_form"]: row["spoken_form"]
            for row in enabled_rules
        }
        self.assertEqual(
            effective,
            {
                "NYC": "Book City",
                "BookOnly": "Book Reading",
                "Mira": "Series Mira",
                "SeriesOnly": "Series Reading",
                "GlobalOnly": "Global Reading",
            },
        )
        self.assertEqual(disabled_rules, [])


if __name__ == "__main__":
    unittest.main()
