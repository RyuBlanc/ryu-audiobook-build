"""Stage 4 Step 2.5: book-level pronunciation aggregation and local learning context."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.ai.brain import AudiobookBrain
from app.core.state import save_state


class OfflineAiLearningContextTests(unittest.TestCase):
    def _brain_with_stubbed_chapters(self, chapters, chapter_results):
        brain = AudiobookBrain.__new__(AudiobookBrain)
        calls = []
        saved_reports = []

        def analyze(chapter, book_context=None, progress=None):
            calls.append((chapter.number, book_context))
            if callable(progress):
                progress(f"Analyzed chapter {chapter.number}")
            return chapter_results[chapter.number]

        brain.analyze_chapter = analyze
        brain._save_book = lambda report: saved_reports.append(report)
        return brain, calls, saved_reports

    def test_book_report_aggregates_chapter_pronunciation_suggestions(self):
        chapters = [
            SimpleNamespace(number=1, title="Opening", text="Haruka arrives."),
            SimpleNamespace(number=2, title="The Shrine", text="Haruka visits the shrine."),
        ]
        chapter_results = {
            1: {
                "chapter": 1, "title": "Opening", "characters": [], "dialogue": [],
                "scenes": [], "pronunciation": [{
                    "written": "Haruka", "spoken": "Hah-roo-kah",
                    "source_language": "Japanese", "script": "Latin",
                    "confidence": 0.91, "reason": "Japanese character name",
                    "alternatives": [],
                }], "continuity_notes": [],
            },
            2: {
                "chapter": 2, "title": "The Shrine", "characters": [], "dialogue": [],
                "scenes": [], "pronunciation": [{
                    "written": "Haruka", "spoken": "Hah-roo-kah",
                    "source_language": "Japanese", "script": "Latin",
                    "confidence": 0.95, "reason": "Repeated character name",
                    "alternatives": [],
                }], "continuity_notes": [],
            },
        }
        brain, _calls, saved = self._brain_with_stubbed_chapters(chapters, chapter_results)

        report = brain.analyze_book(chapters)

        self.assertIn("pronunciation", report)
        self.assertEqual(len(report["pronunciation"]), 1)
        term = report["pronunciation"][0]
        self.assertEqual(term["written"], "Haruka")
        self.assertEqual(term["spoken"], "Hah-roo-kah")
        self.assertEqual(term["confidence"], 0.95)
        self.assertEqual(
            term["occurrences"],
            [
                {"chapter": 1, "chapter_title": "Opening"},
                {"chapter": 2, "chapter_title": "The Shrine"},
            ],
        )
        self.assertEqual(saved[-1]["pronunciation"], report["pronunciation"])

    def test_book_analysis_passes_learning_context_into_each_chapter(self):
        chapters = [
            SimpleNamespace(number=1, title="One", text="Mira speaks."),
            SimpleNamespace(number=2, title="Two", text="Mira returns."),
        ]
        chapter_results = {
            number: {
                "chapter": number, "title": str(number), "characters": [], "dialogue": [],
                "scenes": [], "pronunciation": [], "continuity_notes": [],
            }
            for number in (1, 2)
        }
        brain, calls, _saved = self._brain_with_stubbed_chapters(chapters, chapter_results)
        learning_context = {
            "version": 1,
            "learning_scope": "Slime",
            "pronunciation_memory": [{
                "written_form": "Mira", "spoken_form": "Mee-rah",
                "language": "Japanese", "scope": "series",
            }],
            "speaker_learning_examples": [{
                "speaker": "Mira", "dialogue_text": "I will stay.",
                "source": "explicit-user-confirmation",
            }],
        }

        brain.analyze_book(chapters, learning_context=learning_context)

        self.assertEqual(len(calls), 2)
        for _number, context in calls:
            self.assertIn("characters", context)
            self.assertEqual(context["pronunciation_memory"], learning_context["pronunciation_memory"])
            self.assertEqual(context["speaker_learning_examples"], learning_context["speaker_learning_examples"])

    def test_project_learning_context_merges_book_series_and_global_preferences_in_precedence_order(self):
        from app.ai.learning_context import load_project_learning_context

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "book"
            project.mkdir()
            settings = root / "settings"
            settings.mkdir()
            save_state(project, {
                "series": "Slime",
                "pronunciation_dictionary": [
                    {"written_form": "NYC", "spoken_form": "Book City", "enabled": True},
                    {"written_form": "BookOnly", "spoken_form": "Book Reading", "enabled": True},
                    {"written_form": "Disabled", "spoken_form": "Do Not Learn", "enabled": False},
                ],
            })
            series_key = hashlib.sha256(
                unicodedata.normalize("NFC", "Slime").casefold().encode("utf-8")
            ).hexdigest()
            series_dir = settings / "pronunciation_dictionary_series"
            series_dir.mkdir()
            (series_dir / f"{series_key}.json").write_text(json.dumps([
                {"written_form": "NYC", "spoken_form": "Series City", "enabled": True},
                {"written_form": "SeriesOnly", "spoken_form": "Series Reading", "enabled": True},
            ]), encoding="utf-8")
            (settings / "pronunciation_dictionary_global.json").write_text(json.dumps([
                {"written_form": "NYC", "spoken_form": "Global City", "enabled": True},
                {"written_form": "GlobalOnly", "spoken_form": "Global Reading", "enabled": True},
            ]), encoding="utf-8")
            (settings / "character_learning.json").write_text(json.dumps({
                "version": 1,
                "examples": [
                    {
                        "series": "Slime", "speaker": "Souei",
                        "dialogue_text": "The eastern route is clear.",
                        "context": "Souei checked the eastern route.",
                        "source": "explicit-user-confirmation",
                    },
                    {
                        "series": "Other Series", "speaker": "Other",
                        "dialogue_text": "Different book.",
                        "context": "Different context.",
                        "source": "explicit-user-confirmation",
                    },
                    {
                        "series": "Slime", "speaker": "Unconfirmed",
                        "dialogue_text": "An AI guess.",
                        "context": "Never use this as positive learning.",
                        "source": "ai",
                    },
                ],
            }), encoding="utf-8")

            with patch("app.ai.learning_context.settings_root", return_value=settings), \
                 patch("app.chapters.character_learning.settings_root", return_value=settings):
                context = load_project_learning_context(project)

        self.assertEqual(context["learning_scope"], "Slime")
        effective = {
            row["written_form"]: row["spoken_form"]
            for row in context["pronunciation_memory"]
        }
        self.assertEqual(effective, {
            "NYC": "Book City",
            "BookOnly": "Book Reading",
            "SeriesOnly": "Series Reading",
            "GlobalOnly": "Global Reading",
        })
        self.assertEqual(
            [row["speaker"] for row in context["speaker_learning_examples"]],
            ["Souei"],
        )

    def test_standalone_project_learning_memory_is_book_local(self):
        from app.ai.learning_context import load_project_learning_context

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "StandaloneNovel"
            project.mkdir()
            settings = root / "settings"
            settings.mkdir()
            save_state(project, {})
            (settings / "character_learning.json").write_text(json.dumps({
                "version": 1,
                "examples": [
                    {
                        "series": "book:StandaloneNovel", "speaker": "Mira",
                        "dialogue_text": "Stay close.",
                        "context": "Mira checked the door.",
                        "source": "explicit-user-confirmation",
                    },
                    {
                        "series": "book:OtherNovel", "speaker": "Other",
                        "dialogue_text": "Do not leak.",
                        "context": "Other book.",
                        "source": "explicit-user-confirmation",
                    },
                ],
            }), encoding="utf-8")

            with patch("app.ai.learning_context.settings_root", return_value=settings), \
                 patch("app.chapters.character_learning.settings_root", return_value=settings):
                context = load_project_learning_context(project)

        self.assertEqual(context["learning_scope"], "book:StandaloneNovel")
        self.assertEqual(
            [row["speaker"] for row in context["speaker_learning_examples"]],
            ["Mira"],
        )


if __name__ == "__main__":
    unittest.main()
