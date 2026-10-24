from __future__ import annotations

import unittest

from app.chapters.detector import detect_chapters
from app.documents.parser import reflow_source_text


class ChapterAnalyzerRegressionTests(unittest.TestCase):
    def test_recognizes_common_light_novel_heading_formats(self) -> None:
        source = """Prologue
This opening chapter contains enough narrative text to be identified as real story content.

Chapter One - Return/Attack
The hero entered the ruined hall and looked around carefully before anyone answered him.

Part II: The Hidden Battle
The next section begins with a different setting and a new conflict that changes the entire story.

Volume 2
The second volume begins with a substantial opening passage and several sentences of narrative.

Life.0
This is a supported numbered-life format and it must remain a real chapter boundary.
"""
        chapters = detect_chapters(source)
        self.assertEqual(
            [chapter.title for chapter in chapters],
            ["Prologue", "Chapter One - Return/Attack", "Part II: The Hidden Battle", "Volume 2", "Life.0"],
        )
        self.assertTrue(all(chapter.text.strip() for chapter in chapters))
        self.assertIn("ruined hall", chapters[1].text)
        self.assertNotIn("Chapter One - Return/Attack", chapters[0].text)

    def test_does_not_split_on_narrative_sentences_or_quoted_dialogue(self) -> None:
        source = """Prologue
The opening narrative contains enough words to form a real chapter and establish the setting.

Chapter 1 was something the narrator repeated while walking through the old city.
<<Chapter 2>> appeared as a glowing system message in the air.
“Chapter 3,” he called, “was the name written on the old book.”

Chapter 1 - The Real Beginning
The real chapter starts here and continues with a sufficiently long passage of narrative text.
"""
        chapters = detect_chapters(source)
        self.assertEqual([chapter.title for chapter in chapters], ["Prologue", "Chapter 1 - The Real Beginning"])
        self.assertIn("Chapter 1 was something", chapters[0].text)
        self.assertIn("<<Chapter 2>>", chapters[0].text)
        self.assertIn("“Chapter 3,”", chapters[0].text)

    def test_duplicate_toc_is_not_imported_as_chapters(self) -> None:
        source = """TABLE OF CONTENTS
Prologue
Chapter 1 - Return
Chapter 2 - Attack

Prologue
The actual prologue has a substantive opening passage so the detector can distinguish it from the earlier table-of-contents entry.

Chapter 1 - Return
The hero returned to the station, where his friends were already waiting with questions and worried expressions.

Chapter 2 - Attack
The alarm rang throughout the city as the enemy began another coordinated attack against the defenders.
"""
        chapters = detect_chapters(source)
        self.assertEqual([chapter.title for chapter in chapters], ["Prologue", "Chapter 1 - Return", "Chapter 2 - Attack"])
        all_text = "\n".join(chapter.text for chapter in chapters)
        self.assertNotIn("TABLE OF CONTENTS", all_text)
        self.assertNotIn("Chapter 2 - Attack\n\nPrologue", all_text)
        self.assertIn("actual prologue", chapters[0].text.lower())

    def test_repeated_standalone_slash_titles_are_recognized(self) -> None:
        source = """Introduction
The introductory section contains enough words to provide context before the story's named chapters begin.

Return/Attack
The hero stepped through the doorway and found a familiar room filled with people who had been waiting for him.

Black Dog/Birth
The second scene opened beneath a dark sky as the villagers watched the strange lights move across the mountain.
"""
        chapters = detect_chapters(source)
        self.assertEqual([chapter.title for chapter in chapters], ["Introduction", "Return/Attack", "Black Dog/Birth"])
        self.assertIn("familiar room", chapters[1].text)
        self.assertIn("strange lights", chapters[2].text)

    def test_reflow_keeps_adjacent_dialogue_styles_separate(self) -> None:
        source = '「Wait!」 「Run!」\n<<First signal>> <<Second signal>>'
        result = reflow_source_text(source)
        self.assertIn('「Wait!」\n「Run!」', result)
        self.assertIn('<<First signal>>\n<<Second signal>>', result)


if __name__ == "__main__":
    unittest.main()
