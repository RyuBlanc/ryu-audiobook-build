"""Stage 4 Step 2 offline AI quality: chunk continuity and schema-safe scene parsing."""
from __future__ import annotations

import unittest

from app.ai.brain import AudiobookBrain, BrainConfig


class OfflineAiAnalysisQualityTests(unittest.TestCase):
    def test_long_chapter_chunks_preserve_configured_overlap_and_full_coverage(self):
        brain = AudiobookBrain.__new__(AudiobookBrain)
        brain.config = BrainConfig(context_chars=100, overlap_chars=20)
        source = "".join(chr(65 + (index % 26)) for index in range(250))

        chunks = brain._chunks(source)

        self.assertEqual(chunks[0], source[:100])
        self.assertEqual(chunks[1], source[80:180])
        self.assertEqual(chunks[2], source[160:240])
        self.assertEqual(chunks[3], source[220:250])
        self.assertEqual("".join(chunks[:1]) + "".join(
            chunk[20:] for chunk in chunks[1:]
        ), source)

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

        brain._merge_scenes(result, {
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
        })

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


if __name__ == "__main__":
    unittest.main()
