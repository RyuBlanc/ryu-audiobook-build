from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable

from app.chapters.detector import Chapter
from app.chapters.characters import analyze_chapter as deterministic_character_analysis
from app.chapters.dialogue import dialogue_segments
from app.tts.pronunciation_suggester import COMMON_ENGLISH_WORDS
from .model_runtime import LocalLLM, BrainRuntimeError

class BrainUnavailableError(BrainRuntimeError):
    pass

@dataclass(frozen=True)
class BrainConfig:
    context_chars: int = 12000
    overlap_chars: int = 1400
    max_tokens: int = 2200

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "characters": {
            "type": "array", "maxItems": 12,
            "items": {"type": "object", "additionalProperties": False, "properties": {
                "name": {"type": "string"},
                "aliases": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                "role": {"type": "string"},
                "traits": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
                "voice_direction": {"type": "object", "additionalProperties": False, "properties": {
                    "age_impression": {"type": "string"},
                    "gender": {"type": "string"},
                    "tone": {"type": "string"},
                    "energy": {"type": "string"}
                }, "required": ["age_impression", "gender", "tone", "energy"]},
                "confidence": {"type": "number"}
            }, "required": ["name", "aliases", "role", "traits", "voice_direction", "confidence"]}
        },
        "dialogue": {
            "type": "array", "maxItems": 12,
            "items": {"type": "object", "additionalProperties": False, "properties": {
                "quote": {"type": "string"},
                "speaker": {"type": "string"},
                "confidence": {"type": "number"},
                "evidence": {"type": "string"}
            }, "required": ["quote", "speaker", "confidence", "evidence"]}
        },
        "scenes": {
            "type": "array", "maxItems": 6,
            "items": {"type": "object", "additionalProperties": False, "properties": {
                "summary": {"type": "string"},
                "location": {"type": "string"},
                "time": {"type": "string"},
                "mood": {"type": "string"},
                "narrator_direction": {"type": "object", "additionalProperties": False, "properties": {
                    "pace": {"type": "string"},
                    "energy": {"type": "string"},
                    "delivery": {"type": "string"}
                }, "required": ["pace", "energy", "delivery"]},
                "ambience": {"type": "array", "maxItems": 5, "items": {"type": "string"}},
                "music": {"type": "object", "additionalProperties": False, "properties": {
                    "style": {"type": "string"},
                    "intensity": {"type": "number"}
                }, "required": ["style", "intensity"]},
                "sfx": {"type": "array", "maxItems": 6, "items": {"type": "string"}},
                "confidence": {"type": "number"}
            }, "required": ["summary", "location", "time", "mood", "narrator_direction", "ambience", "music", "sfx", "confidence"]}
        },
        "pronunciation": {
            "type": "array", "maxItems": 8,
            "items": {"type": "object", "additionalProperties": False, "properties": {
                "written": {"type": "string"},
                "spoken": {"type": "string"},
                "ipa": {"type": "string"},
                "source_language": {"type": "string"},
                "script": {"type": "string"},
                "reason": {"type": "string"},
                "confidence": {"type": "number"},
                "alternatives": {"type": "array", "maxItems": 2, "items": {"type": "string"}}
            }, "required": ["written", "spoken", "ipa", "source_language", "script", "reason", "confidence", "alternatives"]}
        },
        "continuity_notes": {"type": "array", "maxItems": 12, "items": {"type": "string"}}
    },
    "required": ["characters", "dialogue", "scenes", "pronunciation", "continuity_notes"]
}

CORE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "characters": {"type": "array", "maxItems": 8, "items": {"type": "object", "additionalProperties": False, "properties": {
            "name": {"type": "string"},
            "aliases": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
            "role": {"type": "string"},
            "traits": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
            "voice_direction": {"type": "object", "additionalProperties": False, "properties": {
                "age_impression": {"type": "string"},
                "gender": {"type": "string"},
                "tone": {"type": "string"},
                "energy": {"type": "string"}
            }, "required": ["age_impression", "gender", "tone", "energy"]},
            "confidence": {"type": "number"}
        }, "required": ["name", "aliases", "role", "traits", "voice_direction", "confidence"]}},
        "dialogue": {"type": "array", "maxItems": 10, "items": {"type": "object", "additionalProperties": False, "properties": {
            "quote": {"type": "string"},
            "speaker": {"type": "string"},
            "confidence": {"type": "number"},
            "evidence": {"type": "string"}
        }, "required": ["quote", "speaker", "confidence", "evidence"]}},
        "pronunciation": {"type": "array", "maxItems": 6, "items": {"type": "object", "additionalProperties": False, "properties": {
            "written": {"type": "string"},
            "spoken": {"type": "string"},
            "ipa": {"type": "string"},
            "source_language": {"type": "string"},
            "script": {"type": "string"},
            "reason": {"type": "string"},
            "confidence": {"type": "number"},
            "alternatives": {"type": "array", "maxItems": 2, "items": {"type": "string"}}
        }, "required": ["written", "spoken", "ipa", "source_language", "script", "reason", "confidence", "alternatives"]}}
    },
    "required": ["characters", "dialogue", "pronunciation"]
}

SCENE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scenes": {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "properties": {
            "summary": {"type": "string"},
            "location": {"type": "string"},
            "time": {"type": "string"},
            "mood": {"type": "string"},
            "narrator_direction": {"type": "object", "additionalProperties": False, "properties": {
                "pace": {"type": "string"},
                "energy": {"type": "string"},
                "delivery": {"type": "string"}
            }, "required": ["pace", "energy", "delivery"]},
            "ambience": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
            "music": {"type": "object", "additionalProperties": False, "properties": {
                "style": {"type": "string"},
                "intensity": {"type": "number"}
            }, "required": ["style", "intensity"]},
            "sfx": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
            "confidence": {"type": "number"}
        }, "required": ["summary", "location", "time", "mood", "narrator_direction", "ambience", "music", "sfx", "confidence"]}},
        "continuity_notes": {"type": "array", "maxItems": 6, "items": {"type": "string"}}
    },
    "required": ["scenes", "continuity_notes"]
}
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
    text = str(text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^\s*```(?:json)?\s*|\s*```\s*$', '', text, flags=re.I | re.S).strip()
    decoder = json.JSONDecoder()
    start = text.find('{')
    if start < 0:
        raise BrainUnavailableError('Audiobook AI did not return a JSON object.')
    try:
        value, _end = decoder.raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise BrainUnavailableError(
            f'Audiobook AI returned malformed JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.'
        ) from exc
    if not isinstance(value, dict):
        raise BrainUnavailableError('Audiobook AI returned a non-object result.')
    return value


def _normalise_pronunciation(item: dict[str, Any], source_text: str) -> dict[str, Any] | None:
    written = str(item.get('written') or item.get('text') or '').strip()
    spoken = str(item.get('spoken') or item.get('pronunciation') or '').strip()
    if not written or not spoken:
        return None
    if written.casefold() not in source_text.casefold():
        return None
    source_language = str(item.get('source_language') or '').strip().casefold()
    confidence = max(0.0, min(1.0, float(item.get('confidence', 0.0) or 0.0)))
    if spoken.casefold() == written.casefold() and not item.get('ipa'):
        return None
    english_phrase = all(
        re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", part or '')
        and part.casefold() in COMMON_ENGLISH_WORDS
        for part in written.split()
    )
    if english_phrase and source_language in {'', 'english', 'en', 'unknown'}:
        return None
    if confidence < 0.80:
        return None
    normalized = dict(item)
    normalized['written'] = written
    normalized['spoken'] = spoken
    normalized['confidence'] = confidence
    normalized.setdefault('ipa', None)
    normalized.setdefault('source_language', None)
    normalized.setdefault('script', 'Latin')
    normalized.setdefault('alternatives', [])
    return normalized

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

    def analyze_chapter(
        self,
        chapter: Chapter,
        book_context: dict[str, Any] | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        text = (chapter.text or '').strip()
        chunks = self._chunks(text)
        result = {'chapter': chapter.number, 'title': chapter.title, 'characters': [], 'dialogue': [], 'scenes': [], 'pronunciation': [], 'continuity_notes': []}
        seen = set()
        for idx, chunk in enumerate(chunks, 1):
            known_characters = [
                str(item.get('name', '')).strip()
                for item in (book_context or {}).get('characters', [])
                if str(item.get('name', '')).strip()
            ]
            common_context = (
                'Known characters from earlier chapters: '
                + json.dumps(known_characters, ensure_ascii=False)
                + '\nChapter: ' + chapter.title
                + f'\nExcerpt {idx}/{len(chunks)}:\n{chunk}'
            )
            if progress:
                progress(f'Analyzing chapter {chapter.number} • excerpt {idx}/{len(chunks)} • character/dialogue pass')
            try:
                core_raw = self.llm.complete(
                    PROMPT + '\nFocus ONLY on characters, dialogue ownership and pronunciation. Return JSON only.',
                    common_context + '\nDo not guess a speaker. Keep dialogue.quote exact. Only include pronunciation terms that truly occur in this excerpt.',
                    max_tokens=1100,
                    temperature=0.05,
                    response_schema=CORE_SCHEMA,
                )
                core_data = _json(core_raw)
            except (BrainRuntimeError, BrainUnavailableError) as exc:
                core_data = self._fallback_core(chapter)
                result.setdefault('warnings', []).append(
                    f'AI core pass fallback for chapter {chapter.number}, excerpt {idx}: {exc}'
                )
            self._merge(result, core_data, seen, source_text=chunk)

            if progress:
                progress(f'Analyzing chapter {chapter.number} • excerpt {idx}/{len(chunks)} • scene pass')
            try:
                scene_raw = self.llm.complete(
                    PROMPT + '\nFocus ONLY on scene mood, narration direction, ambience, music, SFX and continuity. Return JSON only.',
                    common_context + '\nReturn concise production-direction data, not story rewriting.',
                    max_tokens=700,
                    temperature=0.05,
                    response_schema=SCENE_SCHEMA,
                )
                scene_data = _json(scene_raw)
                self._merge(result, scene_data, seen, source_text=chunk)
            except (BrainRuntimeError, BrainUnavailableError) as exc:
                result.setdefault('warnings', []).append(
                    f'AI scene pass skipped for chapter {chapter.number}, excerpt {idx}: {exc}'
                )
            self._save_chapter(result)
        self._save_chapter(result)
        return result

    def _fallback_core(self, chapter: Chapter) -> dict[str, Any]:
        analysis = deterministic_character_analysis(chapter)
        characters = []
        for item in analysis.characters[:12]:
            characters.append({
                'name': item.name,
                'aliases': list(item.aliases),
                'role': item.role,
                'traits': [],
                'voice_direction': {'age_impression': '', 'gender': '', 'tone': '', 'energy': ''},
                'confidence': float(item.confidence),
            })
        dialogue = []
        try:
            segments = dialogue_segments(chapter)
            for segment in segments:
                if segment.suggested_speaker:
                    dialogue.append({
                        'quote': segment.text,
                        'speaker': segment.suggested_speaker,
                        'confidence': float(segment.confidence),
                        'evidence': 'Deterministic speaker analysis fallback.',
                    })
        except Exception:
            pass
        return {'characters': characters, 'dialogue': dialogue, 'pronunciation': []}

    def analyze_book(self, chapters: list[Chapter], progress: Callable[[float, str], None] | None = None) -> dict[str, Any]:
        bible = {}
        results = []
        for idx, chapter in enumerate(chapters, 1):
            def chapter_progress(message: str, idx=idx):
                if progress:
                    # Message is emitted at excerpt boundaries. Estimate within
                    # the current chapter while keeping completed chapters exact.
                    match = re.search(r"excerpt (\d+)/(\d+)", message)
                    if match:
                        excerpt_index = int(match.group(1))
                        excerpt_total = max(1, int(match.group(2)))
                        fraction = ((idx - 1) + ((excerpt_index - 1) / excerpt_total)) / max(1, len(chapters))
                    else:
                        fraction = (idx - 1) / max(1, len(chapters))
                    progress(max(0.0, min(0.999, fraction)), message)

            item = self.analyze_chapter(chapter, bible, progress=chapter_progress)
            results.append(item)
            for char in item.get('characters', []):
                name = str(char.get('name', '')).strip()
                if name:
                    bible.setdefault(name, char)
            self._save_book({'version': 1, 'book_bible': bible, 'chapters': results})
            if progress:
                progress(
                    idx / max(1, len(chapters)),
                    f"Completed chapter {idx}/{len(chapters)} • {chapter.title}",
                )
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

    def _merge(self, out: dict[str, Any], data: dict[str, Any], seen: set[str], source_text: str = '') -> None:
        for key in ('characters', 'scenes'):
            out[key].extend(data.get(key, []) or [])

        existing_pronunciations = {
            str(item.get('written', '')).casefold(): item
            for item in out.get('pronunciation', [])
            if str(item.get('written', '')).strip()
        }
        for item in data.get('pronunciation', []) or []:
            normalized = _normalise_pronunciation(item, source_text)
            if normalized is None:
                continue
            key = normalized['written'].casefold()
            previous = existing_pronunciations.get(key)
            if previous is None or normalized['confidence'] > float(previous.get('confidence', 0.0) or 0.0):
                existing_pronunciations[key] = normalized
        out['pronunciation'] = list(existing_pronunciations.values())
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