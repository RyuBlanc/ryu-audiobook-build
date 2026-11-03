"""Tests for data-driven Stage 4 offline AI report presentation."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.ai_analysis_report import AIAnalysisReportWindow, build_ai_analysis_report_model


class AIAnalysisReportModelTests(unittest.TestCase):
    def test_sections_are_created_only_from_saved_report_data(self):
        model = build_ai_analysis_report_model({
            "analysis_schema_version": 3,
            "learning_scope": "Book local",
            "chapters": [{"chapter": 1}],
            "chapter_summaries": [{
                "chapter": 1, "chapter_title": "The Arrival",
                "summary": "Mira arrives.", "purpose": "Introduce the journey.",
            }],
            "book_themes": [{
                "name": "Courage",
                "observations": [{
                    "chapter": 1, "interpretation": "She chooses to continue.",
                    "confidence": 0.91, "evidence": {
                        "quote": "I will continue.", "start": 12, "end": 28,
                    },
                }],
            }],
            "emotional_arc": [{
                "chapter": 1, "emotion": "resolve", "intensity": 0.8,
                "confidence": 0.9, "note": "A clear decision.",
            }],
            "pronunciation": [{
                "written": "Aelthir", "spoken": "AYL-theer",
                "alternatives": ["EL-theer"], "occurrences": [{"chapter": 1}],
                "confidence": 0.88,
            }],
        })

        self.assertEqual(
            [section["key"] for section in model["sections"]],
            ["chapters", "themes", "emotional_arc", "pronunciation"],
        )
        self.assertEqual(model["counts"]["chapters"], 1)
        self.assertEqual(model["counts"]["themes"], 1)
        self.assertIn("I will continue.", model["sections"][1]["items"][0]["details"][0])
        self.assertIn("Alternative readings: EL-theer", model["sections"][3]["items"][0]["details"])

    def test_empty_or_missing_report_sections_are_not_filled_with_static_samples(self):
        model = build_ai_analysis_report_model({
            "analysis_schema_version": 3,
            "chapters": [],
            "book_themes": [],
            "emotional_arc": [],
            "character_arcs": {},
            "relationships": [],
            "key_events": [],
            "pronunciation": [],
            "continuity_notes": [],
        })
        self.assertEqual(model["sections"], [])
        self.assertFalse(model["has_content"])
        self.assertEqual(model["counts"]["themes"], 0)

    def test_character_arc_and_pronunciation_data_are_rendered_from_nested_records(self):
        model = build_ai_analysis_report_model({
            "character_arcs": {
                "Mira": {"observations": [{
                    "chapter": 2, "motivation": "Protect her friends.",
                    "goal": "Reach the gate.", "change": "Accepts responsibility.",
                }]},
            },
            "pronunciation": [{
                "written": "Mira", "spoken": "MEE-rah", "ipa": "/ˈmɪərə/",
                "source_language": "constructed", "script": "Latin",
                "reason": "Project-confirmed reading.",
                "occurrences": [{"chapter": 2, "chapter_title": "The Gate"}],
                "ambiguous_across_chapters": True, "confidence": 0.95,
            }],
        })
        keys = [section["key"] for section in model["sections"]]
        self.assertEqual(keys, ["character_arcs", "pronunciation"])
        character = model["sections"][0]["items"][0]
        self.assertIn("Accepts responsibility.", character["details"][0])
        pronunciation = model["sections"][1]["items"][0]
        self.assertTrue(any("Review required" in line for line in pronunciation["details"]))
        self.assertTrue(any("Chapter 2" in line for line in pronunciation["details"]))



class AIAnalysisReportWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_loads_saved_report_on_first_open_and_refreshes_dynamic_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            report_path = Path(temp) / "audiobook_brain.json"
            report_path.write_text(json.dumps({
                "analysis_schema_version": 3,
                "learning_scope": "Book local",
                "chapters": [{"chapter": 1}],
                "chapter_summaries": [{
                    "chapter": 1,
                    "chapter_title": "The Arrival",
                    "summary": "Mira arrives at the station.",
                }],
            }), encoding="utf-8")

            window = AIAnalysisReportWindow(report_path)
            try:
                self.assertEqual(window.tabs.count(), 1)
                self.assertEqual(window.tabs.tabText(0), "Chapters")
                self.assertIn("1 chapters", window.meta_label.text())

                report_path.write_text(json.dumps({
                    "analysis_schema_version": 3,
                    "learning_scope": "Book local",
                    "character_arcs": {
                        "Mira": {"observations": [{
                            "chapter": 2,
                            "motivation": "Protect her friends.",
                            "change": "Accepts responsibility.",
                        }]},
                    },
                }), encoding="utf-8")
                window.reload()

                self.assertEqual(window.tabs.count(), 1)
                self.assertEqual(window.tabs.tabText(0), "Character development")
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_window_shows_data_driven_empty_state_when_saved_report_has_no_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            report_path = Path(temp) / "audiobook_brain.json"
            report_path.write_text(json.dumps({
                "analysis_schema_version": 3,
                "chapters": [],
                "book_themes": [],
                "emotional_arc": [],
                "character_arcs": {},
                "relationships": [],
                "key_events": [],
                "pronunciation": [],
                "continuity_notes": [],
            }), encoding="utf-8")

            window = AIAnalysisReportWindow(report_path)
            try:
                self.assertEqual(window.tabs.count(), 1)
                self.assertEqual(window.tabs.tabText(0), "Overview")
                self.assertIn("No report sections contain saved analysis", window.tabs.widget(0).text())
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
