"""Tests for data-driven Stage 4 offline AI report presentation."""
from __future__ import annotations

import unittest

from app.ui.ai_analysis_report import build_ai_analysis_report_model


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


if __name__ == "__main__":
    unittest.main()
