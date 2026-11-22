from __future__ import annotations

import json
import unittest

from app.ai.character_cast import (
    CHARACTER_ONLY_PROMPT,
    CharacterCastAnalyzer,
    build_candidate_inventory,
)
from app.chapters.detector import Chapter


class FakeCharacterLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    def complete(self, system, user, max_tokens=1200, temperature=0.15, response_schema=None):
        self.calls.append((system, user, max_tokens, temperature))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def runtime_info(self):
        return {
            "provider": "llama.cpp",
            "model_id": "qwen3-4b-q4",
            "model_file": "Qwen3-4B-Q4_K_M.gguf",
            "model_identity_verified": True,
        }

    def close(self):
        self.closed = True


class CharacterCastAnalyzerTests(unittest.TestCase):
    def make_analyzer(self, responses):
        analyzer = CharacterCastAnalyzer.__new__(CharacterCastAnalyzer)
        analyzer.project_folder = None
        analyzer.llm = FakeCharacterLLM(responses)
        return analyzer

    @staticmethod
    def character(name, quote, kind="dialogue_attribution", chapter=1, confidence=0.99):
        return {
            "name": name,
            "aliases": [],
            "role": "main",
            "confidence": confidence,
            "evidence": [{"chapter": chapter, "kind": kind, "quote": quote}],
        }

    def test_book_title_and_title_phrase_are_not_candidate_characters(self):
        chapter = Chapter(
            1,
            "The Silver Tower",
            "The Silver Tower\n"
            "Chapter 1: The Silver Tower\n"
            "The Silver Tower stood above the valley.\n"
            "Mira introduced herself. “I am Mira,” she said.",
        )
        inventory = build_candidate_inventory([chapter], metadata_titles=["The Silver Tower"])
        names = {row["name"].casefold() for row in inventory}
        self.assertIn("mira", names)
        self.assertNotIn("the silver tower", names)
        self.assertNotIn("silver tower", names)

    def test_only_whitelisted_name_with_exact_story_evidence_is_returned(self):
        chapter = Chapter(
            1,
            "Chapter 1",
            "“Welcome,” said Mira. Mira smiled at Ren. The Silver Tower stood outside.",
        )
        analyzer = self.make_analyzer([json.dumps({
            "characters": [
                self.character("Mira", "“Welcome,” said Mira.", "dialogue_attribution"),
                self.character("Ren", "Ren fought bravely against the tower.", "named_action"),
                self.character("Silver Tower", "The Silver Tower stood outside.", "named_action"),
            ]
        }, ensure_ascii=False)])
        result = analyzer.analyze_book([chapter], metadata_titles=["The Silver Tower"])
        self.assertEqual([row["name"] for row in result["characters"]], ["Mira"])
        self.assertEqual(result["characters"][0]["evidence"][0]["quote"], "“Welcome,” said Mira.")
        self.assertEqual(result["analysis_mode"], "character_cast_only_v1")
        self.assertNotIn("dialogue", result)
        self.assertNotIn("scenes", result)
        self.assertNotIn("chapter_summary", result)

    def test_high_confidence_cannot_override_fabricated_or_non_source_evidence(self):
        chapter = Chapter(1, "Chapter 1", "“I am Mira,” said Mira. Ren waved from the doorway.")
        analyzer = self.make_analyzer([json.dumps({
            "characters": [
                self.character("Mira", "Mira defeated the Demon King.", "named_action"),
                self.character("Ren", "Ren fought bravely against the tower.", "named_action"),
                self.character("Princess Aurelia", "“I am Mira,” said Mira.", "self_introduction"),
            ]
        }, ensure_ascii=False)])
        result = analyzer.analyze_book([chapter])
        self.assertEqual(result["characters"], [])

    def test_model_cannot_invent_a_character_outside_source_inventory(self):
        chapter = Chapter(1, "Chapter 1", "“I am Mira,” said Mira. Ren waved from the doorway.")
        analyzer = self.make_analyzer([json.dumps({
            "characters": [self.character("Princess Aurelia", "“I am Mira,” said Mira.", "self_introduction")]
        })])
        result = analyzer.analyze_book([chapter])
        self.assertEqual(result["characters"], [])

    def test_japanese_honorific_is_normalised_and_not_returned_as_a_second_character(self):
        chapter = Chapter(
            1,
            "Volume 1",
            "Akari-san waited at the gate. Akari-san greeted her friend. "
            "Akari opened the door and introduced herself as Akari.",
        )
        inventory = build_candidate_inventory([chapter], metadata_titles=["Volume 1"])
        self.assertIn("akari", {row["name"].casefold() for row in inventory})
        self.assertNotIn("akari-san", {row["name"].casefold() for row in inventory})

    def test_japanese_chinese_korean_and_indic_script_speaker_names_are_preserved(self):
        chapter = Chapter(
            1,
            "Multilingual",
            "美咲: 「おはよう。」\n"
            "林晓: “我们走吧。”\n"
            "민수: “안녕하세요.”\n"
            "मीरा: “नमस्ते।”\n"
            "கவிதா: “வணக்கம்।”",
        )
        inventory = build_candidate_inventory([chapter])
        names = {row["name"] for row in inventory}
        expected = {"美咲", "林晓", "민수", "मीरा", "கவிதா"}
        self.assertTrue(expected.issubset(names))
        payload = {
            "characters": [
                self.character(
                    name,
                    next(line for line in chapter.text.splitlines() if line.startswith(name)),
                    "speaker_label",
                    confidence=0.97,
                )
                for name in sorted(expected)
            ]
        }
        analyzer = self.make_analyzer([json.dumps(payload, ensure_ascii=False)])
        result = analyzer.analyze_book([chapter])
        self.assertEqual({row["name"] for row in result["characters"]}, expected)

    def test_model_failure_retries_once_then_uses_only_explicit_source_speaker_labels(self):
        chapter = Chapter(1, "Chapter 1", "Mira: “Hello.”\nThe Silver Tower was quiet.")
        analyzer = self.make_analyzer([RuntimeError("invalid response"), RuntimeError("repair failed")])
        result = analyzer.analyze_book([chapter], metadata_titles=["The Silver Tower"])
        self.assertEqual(len(analyzer.llm.calls), 2)
        self.assertEqual([row["name"] for row in result["characters"]], ["Mira"])
        self.assertTrue(result["warnings"])
        self.assertEqual(result["coverage"]["processed_chapters"], 1)

    def test_all_candidate_batches_are_processed_without_silent_limit(self):
        lines = []
        for index in range(30):
            name = f"Character{index:02d}"
            lines.append(f'{name}: “I am {name}.”')
        chapter = Chapter(1, "Many characters", "\n".join(lines))
        inventory = build_candidate_inventory([chapter])
        self.assertGreaterEqual(len(inventory), 25)
        analyzer = self.make_analyzer([
            json.dumps({"characters": []}),
            json.dumps({"characters": []}),
        ])
        result = analyzer.analyze_book([chapter])
        self.assertEqual(len(analyzer.llm.calls), 2)
        self.assertEqual(result["coverage"]["model_batch_count"], 2)
        self.assertEqual(result["coverage"]["model_request_count"], 2)
        self.assertEqual(result["performance"]["model_request_count"], 2)
        self.assertEqual(result["coverage"]["candidate_count"], len(inventory))
        self.assertTrue(result["coverage"]["coverage_complete"])
        self.assertFalse(result["coverage"]["truncated"])

    def test_prompt_is_character_only_and_contains_multilingual_calibration(self):
        prompt = CHARACTER_ONLY_PROMPT.casefold()
        for expected in (
            "japanese light novels",
            "english novels",
            "chinese",
            "korean",
            "devanagari",
            "tamil",
            "never return",
            "strict evidence requirements",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, prompt)

    def test_model_runtime_identity_is_returned_with_cast_report(self):
        chapter = Chapter(1, "Chapter 1", 'Mira: “Ready?”')
        analyzer = self.make_analyzer([json.dumps({
            "characters": [self.character("Mira", 'Mira: “Ready?”', "speaker_label", confidence=0.95)]
        })])
        result = analyzer.analyze_book([chapter])
        self.assertEqual(result["runtime"]["model_id"], "qwen3-4b-q4")
        self.assertTrue(result["runtime"]["model_identity_verified"])


if __name__ == "__main__":
    unittest.main()
