from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable

from app.chapters.detector import Chapter
from .model_runtime import LocalLLM, BrainRuntimeError

class BrainUnavailableError(BrainRuntimeError):
    pass

@dataclass(frozen=True)
class BrainConfig:
    context_chars: int = 12000
    overlap_chars: int = 1400
    max_tokens: int = 2200

PROMPT = '''You are Ryu's Audiobook Director. Analyze the supplied novel excerpt only.
Return JSON. Do not invent facts. Identify canonical characters and aliases, exact dialogue and likely speaker with confidence and evidence, scene boundaries, location, time, mood, narrator delivery, character delivery, pacing, pronunciation hints, ambience, music, SFX, and continuity notes.

Pronunciation is critical. Detect unusual names, fictional names, place names, honorifics, food, cultural terms, spells, titles, organizations and borrowed words from Japanese, Korean, Hindi, Tamil, Telugu, Malayalam, Kannada, Bengali, Marathi, Chinese, Spanish, French and other languages when the evidence supports it. Also detect romanized/transliterated words such as Japanese or Korean names written with Latin letters.

Do NOT create pronunciation overrides for ordinary English words just because they are capitalized. Do not guess a pronunciation when the evidence is weak.

For every pronunciation candidate return:
- written: exact text as it appears in the book
- spoken: an English-readable spoken form for the selected narrator voice
- ipa: IPA when you are confident; otherwise null
- source_language: likely source language or language family, or null
- script: Latin, Hiragana/Katakana, Kanji, Hangul, Devanagari, Tamil, etc.
- confidence: 0.0 to 1.0
- reason: concise evidence for the pronunciation
- alternatives: up to 2 plausible alternatives if ambiguity exists

When the same name appears with different spellings, treat them as aliases and keep one canonical pronunciation entry.

JSON keys: characters, dialogue, scenes, pronunciation, continuity_notes.
Dialogue items: quote, speaker, confidence, evidence.
Characters: name, aliases, role, traits, voice_direction, confidence.
Scenes: summary, location, time, mood, narrator_direction, ambience, music, sfx, confidence.
Pronunciation: written, spoken, ipa, source_language, script, reason, confidence, alternatives.'''

def _json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith('```'):
        text = text.strip('`').removeprefix('json').strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise BrainUnavailableError('Audiobook AI did not return JSON.')
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise BrainUnavailableError('Audiobook AI returned a non-object result.')
    return value

class AudiobookBrain:
    def __init__(self, project_folder: Path, config: BrainConfig | None = None):
        self.project_folder = project_folder
        self.config = config or BrainConfig()
        self.analysis_dir = project_folder / 'analysis'
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.output_file = self.analysis_dir / 'audiobook_brain.json'
        try:
            self.llm = LocalLLM()
        except BrainRuntimeError as exc:
            raise BrainUnavailableError(str(exc)) from exc

    def close(self) -> None:
        self.llm.close()

    def analyze_chapter(self, chapter: Chapter, book_context: dict[str, Any] | None = None) -> dict[str, Any]:
        text = (chapter.text or '').strip()
        chunks = self._chunks(text)
        result = {'chapter': chapter.number, 'title': chapter.title, 'characters': [], 'dialogue': [], 'scenes': [], 'pronunciation': [], 'continuity_notes': []}
        seen = set()
        for idx, chunk in enumerate(chunks, 1):
            user = ('Book context: ' + json.dumps(book_context or {}, ensure_ascii=False) +
                    '\nChapter: ' + chapter.title + f'\nExcerpt {idx}/{len(chunks)}:\n' + chunk +
                    '\nKeep dialogue quotes exact and do not guess a speaker without evidence.')
            data = _json(self.llm.complete(PROMPT, user, max_tokens=self.config.max_tokens, temperature=0.12))
            self._merge(result, data, seen)
        self._save_chapter(result)
        return result

    def analyze_book(self, chapters: list[Chapter], progress: Callable[[int, int, str], None] | None = None) -> dict[str, Any]:
        bible = {}
        results = []
        for idx, chapter in enumerate(chapters, 1):
            item = self.analyze_chapter(chapter, bible)
            results.append(item)
            for char in item.get('characters', []):
                name = str(char.get('name', '')).strip()
                if name:
                    bible.setdefault(name, char)
            self._save_book({'version': 1, 'book_bible': bible, 'chapters': results})
            if progress:
                progress(idx, len(chapters), chapter.title)
        return {'version': 1, 'book_bible': bible, 'chapters': results}

    def _chunks(self, text: str) -> list[str]:
        if len(text) <= self.config.context_chars:
            return [text]
        out, start = [], 0
        while start < len(text):
            end = min(len(text), start + self.config.context_chars)
            out.append(text[start:end])
            if end >= len(text): break
            start = max(end - self.config.overlap_chars, end)
        return out

    def _merge(self, out: dict[str, Any], data: dict[str, Any], seen: set[str]) -> None:
        for key in ('characters', 'scenes'):
            out[key].extend(data.get(key, []) or [])

        existing_pronunciations = {
            str(item.get("written", "")).casefold(): item
            for item in out.get("pronunciation", [])
            if str(item.get("written", "")).strip()
        }
        for item in data.get("pronunciation", []) or []:
            written = str(item.get("written") or item.get("text") or "").strip()
            spoken = str(item.get("spoken") or item.get("pronunciation") or "").strip()
            if not written or not spoken:
                continue
            key = written.casefold()
            previous = existing_pronunciations.get(key)
            if previous is None or float(item.get("confidence", 0.0) or 0.0) > float(previous.get("confidence", 0.0) or 0.0):
                normalized = dict(item)
                normalized["written"] = written
                normalized["spoken"] = spoken
                normalized.setdefault("ipa", None)
                normalized.setdefault("source_language", None)
                normalized.setdefault("script", "Latin")
                normalized.setdefault("alternatives", [])
                existing_pronunciations[key] = normalized
        out["pronunciation"] = list(existing_pronunciations.values())
        for item in data.get('dialogue', []) or []:
            quote = str(item.get('quote', '')).strip()
            if quote and quote.casefold() not in seen:
                out['dialogue'].append(item); seen.add(quote.casefold())
        for note in data.get('continuity_notes', []) or []:
            if note not in out['continuity_notes']:
                out['continuity_notes'].append(note)

    def _save_chapter(self, data: dict[str, Any]) -> None:
        path = self.analysis_dir / f"chapter_{int(data['chapter']):04d}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _save_book(self, data: dict[str, Any]) -> None:
        self.output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')