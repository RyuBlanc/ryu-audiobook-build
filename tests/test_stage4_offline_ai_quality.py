"""Stage 4 Step 2 offline AI quality: chunk continuity and schema-safe scene parsing."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from pathlib import Path

from app.ai.brain import AudiobookBrain, BrainConfig


class OfflineAiAnalysisQualityTests(unittest.TestCase):

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

    def test_long_chapter_chunks_preserve_configured_overlap_and_full_coverage(self):
        brain = AudiobookBrain.__new__(AudiobookBrain)
        brain.config = BrainConfig(context_chars=100, overlap_chars=20)
        source = "".join(chr(65 + (index % 26)) for index in range(250))

        chunks = brain._chunks(source)

        self.assertEqual(chunks[0], source[:100])
        self.assertEqual(chunks[1], source[80:180])
        self.assertEqual(chunks[2], source[160:250])
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0] + chunks[1][20:] + chunks[2][20:], source)

    def test_scene_merge_reads_nested_schema_for_narrator_and_music_direction(self):
        brain = AudiobookBrain.__new__(AudiobookBrain)
        result = {
            "chapter": 1,
            "title": "The Storm",
            "characters": [],
            "dialogue": [],
            "scenes": [],
            "pronunciation": [],
            "continuity_notes": [],
        }

        scene_payload = {
            "scenes": [{
                "summary": "The protagonist enters the abandoned station.",
                "location": "Abandoned station",
                "time": "Night",
                "mood": "uneasy anticipation",
                "narrator_direction": {
                    "pace": "slow, controlled",
                    "energy": "restrained",
                    "delivery": "quiet tension with a slight breath",
                },
                "ambience": ["distant rain", "faint electrical hum"],
                "music": {"style": "low dark strings", "intensity": 0.72},
                "sfx": ["metal door creak"],
                "confidence": 0.93,
            }],
            "continuity_notes": ["The station's power is already out."],
        }
        brain._merge_scenes(result, scene_payload)

        scene = result["scenes"][0]
        self.assertEqual(scene["narrator_direction"], {
            "pace": "slow, controlled",
            "energy": "restrained",
            "delivery": "quiet tension with a slight breath",
        })
        self.assertEqual(scene["music"], {
            "style": "low dark strings",
            "intensity": 0.72,
        })
        self.assertEqual(scene["mood"], "uneasy anticipation")
        self.assertEqual(scene["ambience"], ["distant rain", "faint electrical hum"])
        self.assertEqual(scene["sfx"], ["metal door creak"])
        self.assertEqual(scene["confidence"], 0.93)

    def test_scene_merge_remains_compatible_with_legacy_flat_scene_payloads(self):
        brain = AudiobookBrain.__new__(AudiobookBrain)
        result = {"scenes": [], "continuity_notes": []}

        brain._merge_scenes(result, {
            "scenes": [{
                "summary": "A quiet room.",
                "pace": "slow",
                "energy": "low",
                "delivery": "soft",
                "music_style": "ambient piano",
                "music_intensity": 0.25,
                "confidence": 0.8,
            }]
        })

        self.assertEqual(result["scenes"][0]["narrator_direction"]["pace"], "slow")
        self.assertEqual(result["scenes"][0]["narrator_direction"]["delivery"], "soft")
        self.assertEqual(result["scenes"][0]["music"]["style"], "ambient piano")
        self.assertEqual(result["scenes"][0]["music"]["intensity"], 0.25)


    def test_story_facts_require_exact_chapter_evidence_and_record_absolute_offsets(self):
        from app.chapters.detector import Chapter

        brain = AudiobookBrain.__new__(AudiobookBrain)
        source = (
            "Mira gripped the letter. "
            "“I will not run.” "
            "Ren looked away. "
            "The room went silent."
        )
        start_offset = 1200
        result = {
            "chapter": 4,
            "title": "The Letter",
            "characters": [],
            "dialogue": [],
            "scenes": [],
            "pronunciation": [],
            "continuity_notes": [],
            "themes": [],
            "emotional_beats": [],
            "key_events": [],
            "character_observations": [],
            "relationships": [],
        }
        brain._merge(
            result,
            {
                "characters": [{
                    "name": "Mira", "aliases": [], "role": "Protagonist",
                    "traits": ["determined"], "voice_direction": {
                        "age_impression": "", "gender": "", "tone": "", "energy": ""
                    }, "confidence": 0.94,
                }, {
                    "name": "Ren", "aliases": [], "role": "Companion",
                    "traits": ["guarded"], "voice_direction": {
                        "age_impression": "", "gender": "", "tone": "", "energy": ""
                    }, "confidence": 0.91,
                }],
                "themes": [
                    {
                        "name": "Resolve",
                        "interpretation": "Mira chooses to face the danger.",
                        "evidence_quote": "“I will not run.”",
                        "confidence": 0.93,
                    },
                    {
                        "name": "Fabricated",
                        "interpretation": "Unsupported statement.",
                        "evidence_quote": "The king destroyed the northern bridge.",
                        "confidence": 0.99,
                    },
                ],
                "emotional_beats": [
                    {
                        "emotion": "determination", "intensity": 0.82,
                        "note": "A firm refusal to retreat.",
                        "evidence_quote": "“I will not run.”",
                        "confidence": 0.92,
                    },
                    {
                        "emotion": "false fear", "intensity": 0.99,
                        "note": "Invented line.",
                        "evidence_quote": "Mira screamed and fled.",
                        "confidence": 0.99,
                    },
                ],
                "key_events": [{
                    "event": "Mira refuses to retreat.",
                    "event_type": "decision",
                    "evidence_quote": "“I will not run.”",
                    "confidence": 0.94,
                }],
                "character_observations": [{
                    "character": "Mira",
                    "motivation": "Protect her companions.",
                    "goal": "Continue despite the threat.",
                    "change": "Moves from hesitation to resolve.",
                    "evidence_quote": "Mira gripped the letter.",
                    "confidence": 0.9,
                }],
                "relationships": [{
                    "character_a": "Mira", "character_b": "Ren",
                    "dynamic": "Mira takes responsibility while Ren withdraws.",
                    "evidence_quote": "Ren looked away.",
                    "confidence": 0.86,
                }],
            },
            set(),
            source_text=source,
            source_offset=start_offset,
        )

        self.assertEqual([item["name"] for item in result["themes"]], ["Resolve"])
        self.assertEqual([item["emotion"] for item in result["emotional_beats"]], ["determination"])
        expected_start = start_offset + source.index("“I will not run.”")
        self.assertEqual(result["themes"][0]["evidence"]["start"], expected_start)
        self.assertEqual(result["themes"][0]["evidence"]["end"], expected_start + len("“I will not run.”"))
        self.assertEqual(result["key_events"][0]["evidence"]["quote"], "“I will not run.”")
        self.assertEqual(result["character_observations"][0]["character"], "Mira")
        self.assertEqual(result["relationships"][0]["character_b"], "Ren")

    def test_book_report_aggregates_themes_emotional_arc_and_character_development(self):
        chapters = [
            SimpleNamespace(number=1, title="The Arrival", text="Mira arrives."),
            SimpleNamespace(number=2, title="The Choice", text="Mira decides."),
        ]
        chapter_results = {
            1: {
                "chapter": 1, "title": "The Arrival", "characters": [
                    {"name": "Mira", "traits": ["cautious"], "confidence": 0.9}
                ], "dialogue": [], "scenes": [], "pronunciation": [],
                "continuity_notes": [], "chapter_summary": "Mira arrives cautiously.",
                "chapter_purpose": "Introduce Mira's fear of the journey.",
                "themes": [{
                    "name": "Courage", "interpretation": "Courage begins with uncertainty.",
                    "confidence": 0.8, "evidence": {
                        "quote": "Mira arrives.", "start": 0, "end": 13
                    },
                }],
                "emotional_beats": [{
                    "emotion": "uncertainty", "intensity": 0.35,
                    "confidence": 0.8, "evidence": {
                        "quote": "Mira arrives.", "start": 0, "end": 13
                    },
                }],
                "character_observations": [{
                    "character": "Mira", "motivation": "Stay safe.",
                    "goal": "Avoid the journey.", "change": "Still cautious.",
                    "confidence": 0.8, "evidence": {
                        "quote": "Mira arrives.", "start": 0, "end": 13
                    },
                }],
                "key_events": [], "relationships": [],
            },
            2: {
                "chapter": 2, "title": "The Choice", "characters": [
                    {"name": "Mira", "traits": ["determined"], "confidence": 0.95}
                ], "dialogue": [], "scenes": [], "pronunciation": [],
                "continuity_notes": [], "chapter_summary": "Mira chooses to continue.",
                "chapter_purpose": "Show the first change in her resolve.",
                "themes": [{
                    "name": "Courage", "interpretation": "Mira chooses action.",
                    "confidence": 0.92, "evidence": {
                        "quote": "Mira decides.", "start": 0, "end": 13
                    },
                }],
                "emotional_beats": [{
                    "emotion": "determination", "intensity": 0.82,
                    "confidence": 0.92, "evidence": {
                        "quote": "Mira decides.", "start": 0, "end": 13
                    },
                }],
                "character_observations": [{
                    "character": "Mira", "motivation": "Protect her companions.",
                    "goal": "Continue the journey.", "change": "Moves from caution to resolve.",
                    "confidence": 0.92, "evidence": {
                        "quote": "Mira decides.", "start": 0, "end": 13
                    },
                }],
                "key_events": [], "relationships": [],
            },
        }
        brain, _calls, _saved = self._brain_with_stubbed_chapters(chapters, chapter_results)

        report = brain.analyze_book(chapters)

        self.assertEqual(report["book_themes"][0]["name"], "Courage")
        self.assertEqual(len(report["book_themes"][0]["observations"]), 2)
        self.assertEqual(
            [item["emotion"] for item in report["emotional_arc"]],
            ["uncertainty", "determination"],
        )
        arc = report["character_arcs"]["Mira"]
        self.assertEqual(len(arc["observations"]), 2)
        self.assertIn("Moves from caution to resolve.", arc["observations"][-1]["change"])
        self.assertEqual(len(report["chapters"]), 2)



if __name__ == "__main__":
    unittest.main()
