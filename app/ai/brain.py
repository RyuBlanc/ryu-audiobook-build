from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Callable

from app.chapters.detector import Chapter
from app.chapters.characters import analyze_chapter as deterministic_character_analysis
from app.chapters.dialogue import dialogue_segments
from app.tts.pronunciation_suggester import COMMON_ENGLISH_WORDS, is_common_english_phrase, nativeish_pronunciation
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
            "type": "array", "maxItems": 16,
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
        "chapter_summary": {"type": "string"},
        "chapter_purpose": {"type": "string"},
        "chapter_purpose_evidence": {"type": "string"},
        "themes": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "additionalProperties": false, "properties": {
                "name": {"type": "string"}, "interpretation": {"type": "string"},
                "evidence_quote": {"type": "string"}, "confidence": {"type": "number"}
            }
        }},
        "emotional_beats": {"type": "array", "maxItems": 5, "items": {
            "type": "object", "additionalProperties": false, "properties": {
                "emotion": {"type": "string"}, "intensity": {"type": "number"},
                "note": {"type": "string"}, "evidence_quote": {"type": "string"},
                "confidence": {"type": "number"}
            }
        }},
        "key_events": {"type": "array", "maxItems": 6, "items": {
            "type": "object", "additionalProperties": false, "properties": {
                "event": {"type": "string"}, "event_type": {"type": "string"},
                "evidence_quote": {"type": "string"}, "confidence": {"type": "number"}
            }
        }},
        "character_observations": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": false, "properties": {
                "character": {"type": "string"}, "motivation": {"type": "string"},
                "goal": {"type": "string"}, "change": {"type": "string"},
                "evidence_quote": {"type": "string"}, "confidence": {"type": "number"}
            }
        }},
        "relationships": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "additionalProperties": false, "properties": {
                "character_a": {"type": "string"}, "character_b": {"type": "string"},
                "dynamic": {"type": "string"}, "evidence_quote": {"type": "string"},
                "confidence": {"type": "number"}
            }
        }},
        "pronunciation": {"type": "array", "maxItems": 12, "items": {"type": "object", "additionalProperties": False, "properties": {
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

Do NOT create pronunciation overrides for ordinary English words, common titles, or ordinary English phrases. A language label alone is NOT enough to override an English word. Do not guess a pronunciation when the evidence is weak.
For romanized Japanese/Korean names, prefer the native sound represented by the original language. Examples: Japanese "Hinata" should be closer to "hee-nah-tah" than "hi-Na-Ta"; Korean "Hyeon-woo" should be closer to "hyun-oo".

For every pronunciation candidate return:
- written: exact text as it appears in the book
- spoken: a TTS-friendly native-ish phonetic form for the selected narrator voice. Do NOT spell every letter separately and do NOT capitalize each syllable.
- ipa: native IPA when you are confident; otherwise null
- source_language: likely source language or language family, or null
- script: Latin, Hiragana/Katakana, Kanji, Hangul, Devanagari, Tamil, etc.
- confidence: 0.0 to 1.0
- reason: concise evidence for the pronunciation
- prioritize character names, aliases, place names, invented terms, and genuinely non-obvious foreign words
- do not spend pronunciation slots on ordinary English words; return as many useful high-confidence entries as the schema allows
- alternatives: up to 2 plausible alternatives if ambiguity exists
- prioritize character names, aliases, places, invented terms, and genuinely non-obvious foreign words
- never spend pronunciation slots on ordinary English vocabulary

When the same name appears with different spellings, treat them as aliases and keep one canonical pronunciation entry.

JSON keys: characters, dialogue, scenes, pronunciation, continuity_notes.
Dialogue items: quote, speaker, confidence, evidence.
Characters: name, aliases, role, traits, voice_direction, confidence.
Scenes: summary, location, time, mood, narrator_direction, ambience, music, sfx, confidence.
Pronunciation: written, spoken, ipa, source_language, script, reason, confidence, alternatives.'''

def _json(text: str) -> dict[str, Any]:
    text = str(text or '').strip()
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.I | re.S).strip()
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


def _numeric_score(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    text = str(value or "").strip().casefold()
    mapping = {
        "none": 0.0,
        "very low": 0.15,
        "low": 0.25,
        "moderate": 0.5,
        "medium": 0.5,
        "high": 0.75,
        "very high": 0.9,
        "certain": 1.0,
        "very confident": 0.9,
        "confident": 0.8,
        "likely": 0.75,
        "possible": 0.5,
        "uncertain": 0.35,
    }
    if text in mapping:
        return mapping[text]
    try:
        return max(0.0, min(1.0, float(text)))
    except (TypeError, ValueError):
        return 0.0


def _normalise_pronunciation(item: dict[str, Any], source_text: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    written = str(item.get('written') or item.get('text') or '').strip()
    spoken = str(item.get('spoken') or item.get('pronunciation') or '').strip()
    if not written or not spoken:
        return None
    if written.casefold() not in source_text.casefold():
        return None
    source_language = str(item.get('source_language') or '').strip().casefold()
    confidence = _numeric_score(item.get('confidence', 0.0))
    ipa = str(item.get('ipa') or '').strip() or None
    if spoken.casefold() == written.casefold() and not ipa:
        return None

    # Hard safety gate: ordinary English vocabulary should never become a
    # pronunciation override merely because the model mislabeled its language.
    if is_common_english_phrase(written):
        return None

    if confidence < 0.80:
        return None

    normalized = dict(item)
    normalized['written'] = written
    # Preserve the AI-generated spoken form when it is present and distinct.
    # A deterministic nativeish fallback is useful only when the model failed to
    # provide a usable spoken form; overwriting a good model result with a rough
    # transliteration was making some Japanese/Korean/Chinese names less accurate.
    normalized['spoken'] = spoken
    if not normalized['spoken'] or normalized['spoken'].casefold() == written.casefold():
        nativeish = nativeish_pronunciation(written, source_language)
        if nativeish:
            normalized['spoken'] = nativeish
    normalized['confidence'] = confidence
    normalized['ipa'] = ipa
    normalized.setdefault('source_language', source_language or None)
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
        original_text = chapter.text or ''
        leading_source_offset = len(original_text) - len(original_text.lstrip())
        text = original_text.strip()
        result = {
            'chapter': chapter.number, 'title': chapter.title,
            'characters': [], 'dialogue': [], 'scenes': [], 'pronunciation': [],
            'continuity_notes': [], 'themes': [], 'emotional_beats': [],
            'key_events': [], 'character_observations': [], 'relationships': [],
            'chapter_summary': '', 'chapter_purpose': '',
        }
        if not text:
            result['warnings'] = [
                f'Chapter {chapter.number} has no body text; AI analysis was skipped.'
            ]
            self._save_chapter(result)
            return result
        chunks = self._chunks(text)
        window_chars = max(1, int(self.config.context_chars))
        overlap_chars = min(max(0, int(self.config.overlap_chars)), window_chars - 1)
        chunk_stride = window_chars - overlap_chars
        seen = set()
        for idx, chunk in enumerate(chunks, 1):
            source_offset = leading_source_offset + (idx - 1) * chunk_stride
            context = book_context or {}
            if isinstance(context.get("characters"), list):
                known_characters = [
                    str(item.get("name", "")).strip()
                    for item in context.get("characters", [])
                    if str(item.get("name", "")).strip()
                ]
            else:
                known_characters = [
                    str(name).strip()
                    for name in context.keys()
                    if str(name).strip() and str(name).strip().casefold() not in {"version", "continuity_notes"}
                ]
            common_context = (
                'Known characters from earlier chapters: '
                + json.dumps(known_characters, ensure_ascii=False)
                + '\nChapter: ' + chapter.title
                + f'\nExcerpt {idx}/{len(chunks)}:\n{chunk}'
            )
            pronunciation_memory = context.get("pronunciation_memory")
            if isinstance(pronunciation_memory, list) and pronunciation_memory:
                common_context += (
                    '\nUser-approved pronunciation memory (use the exact saved spoken form '
                    'when the written term matches; do not silently replace it with a guess): '
                    + json.dumps(pronunciation_memory[:40], ensure_ascii=False)
                )
            speaker_memory = context.get("speaker_learning_examples")
            if isinstance(speaker_memory, list) and speaker_memory:
                common_context += (
                    '\nPreviously confirmed speaker examples from this same book/series. '
                    'Use them only as contextual evidence; never auto-assign a speaker or '
                    'override an explicit local source tag: '
                    + json.dumps(speaker_memory[:16], ensure_ascii=False)
                )
            if progress:
                progress(f'Analyzing chapter {chapter.number} • excerpt {idx}/{len(chunks)} • character/dialogue pass')
            try:
                core_raw = self.llm.complete(
                    PROMPT + (
                        '\nAnalyze characters, dialogue ownership, pronunciation and chapter story. '
                        'Return chapter_summary, chapter_purpose, themes, emotional_beats, key_events, '
                        'character_observations and relationships as well as the existing fields. '
                        'Every story observation must have evidence_quote copied exactly from this excerpt. '
                        'Do not invent events, motives or dialogue. Omit unsupported observations. JSON only.'
                    ),
                    '/no_think ' + common_context + (
                        '\nDo not guess a speaker. Keep dialogue.quote exact. Only include pronunciation '
                        'terms that truly occur in this excerpt. For each theme, emotional beat, key event, '
                        'character observation and relationship, include a short exact evidence_quote from '
                        'this excerpt. Omit any item without direct textual evidence.'
                    ),
                    max_tokens=2000,
                    temperature=0.05,
                    response_schema=CORE_SCHEMA,
                )
                core_data = _json(core_raw)
            except (BrainRuntimeError, BrainUnavailableError) as first_error:
                # Qwen can occasionally stop inside a JSON string even though
                # inference itself succeeded. Retry with a much smaller,
                # repair-only prompt before falling back to deterministic
                # analysis. This avoids marking a healthy AI runtime as failed
                # because of one malformed generation.
                try:
                    repair_raw = self.llm.complete(
                        'Return ONLY one compact valid JSON object with keys characters, dialogue, pronunciation. '
                        'Do not use markdown. Do not add explanations. Do not guess.',
                        '/no_think Extract only the factual character, dialogue and pronunciation information from this excerpt. '
                        'Preserve exact dialogue quotes. Use at most 12 pronunciation entries and keep each reason very short. '
                        f'Chapter: {chapter.title}\nExcerpt:\n{chunk}',
                        max_tokens=1500,
                        temperature=0.0,
                        response_schema=CORE_SCHEMA,
                    )
                    core_data = _json(repair_raw)
                except (BrainRuntimeError, BrainUnavailableError) as second_error:
                    core_data = self._fallback_core(chapter)
                    result.setdefault('warnings', []).append(
                        f'AI core pass fallback for chapter {chapter.number}, excerpt {idx}: {second_error}'
                    )
            self._merge(
                result, core_data, seen,
                source_text=chunk,
                source_offset=source_offset,
            )

            if progress:
                progress(f'Analyzing chapter {chapter.number} • excerpt {idx}/{len(chunks)} • scene pass')
            scene_prompt = (
                'Analyze ONLY scene direction for an audiobook. Return one compact JSON object with keys '
                'scenes and continuity_notes. Each scene must contain summary, location, time, mood, '
                'narrator_direction (an object with pace, energy, delivery), ambience (an array), '
                'music (an object with style and numeric intensity from 0 to 1), sfx (an array), '
                'and confidence (0 to 1). Use short phrases, keep every field in this exact nested shape, '
                'and never include unsupported facts. JSON only.'
            )
            scene_user = (
                f'Chapter: {chapter.title}\nExcerpt:\n{chunk}\n'
                'Do not retell the story. Do not invent facts. Keep this under 450 output tokens.'
            )
            try:
                scene_raw = self.llm.complete(
                    scene_prompt,
                    '/no_think ' + scene_user,
                    max_tokens=500,
                    temperature=0.0,
                    response_schema=SCENE_SCHEMA,
                )
                scene_data = _json(scene_raw)
                self._merge_scenes(result, scene_data)
            except (BrainRuntimeError, BrainUnavailableError) as first_error:
                try:
                    repair = self.llm.complete(
                        'Return only compact valid JSON for audiobook scene direction. Keys: scenes, continuity_notes.',
                        '/no_think ' + scene_user + '\nPrevious output was malformed. Produce valid JSON only.',
                        max_tokens=450,
                        temperature=0.0,
                        response_schema=SCENE_SCHEMA,
                    )
                    scene_data = _json(repair)
                    self._merge_scenes(result, scene_data)
                except (BrainRuntimeError, BrainUnavailableError) as second_error:
                    # Scene direction is advisory; deterministic character/dialogue/
                    # pronunciation analysis remains authoritative. Keep the book usable
                    # and surface the issue in the saved diagnostic instead of aborting.
                    result.setdefault('warnings', []).append(
                        f'AI scene pass skipped for chapter {chapter.number}, excerpt {idx}: {second_error}'
                    )
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

    def analyze_book(
        self,
        chapters: list[Chapter],
        progress: Callable[[float, str], None] | None = None,
        learning_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze chapters in sequence and persist one backward-compatible book report."""
        bible: dict[str, dict[str, Any]] = {}
        results: list[dict[str, Any]] = []
        base_context = dict(learning_context or {})
        pronunciation_by_key: dict[str, dict[str, Any]] = {}

        def aggregate_pronunciation() -> list[dict[str, Any]]:
            aggregated: list[dict[str, Any]] = []
            for item in pronunciation_by_key.values():
                aggregated.append(item)
            return aggregated

        def build_report() -> dict[str, Any]:
            continuity: list[str] = []
            themes_by_key: dict[str, dict[str, Any]] = {}
            emotional_arc: list[dict[str, Any]] = []
            character_arcs: dict[str, dict[str, Any]] = {}
            relationship_rows: list[dict[str, Any]] = []
            key_events: list[dict[str, Any]] = []
            chapter_summaries: list[dict[str, Any]] = []

            for chapter_result in results:
                number = int(chapter_result.get("chapter") or 0)
                title = str(chapter_result.get("title") or "")
                summary = str(chapter_result.get("chapter_summary") or "").strip()
                purpose = str(chapter_result.get("chapter_purpose") or "").strip()
                if summary or purpose:
                    chapter_summaries.append({
                        "chapter": number, "chapter_title": title,
                        "summary": summary, "purpose": purpose,
                    })
                for note in chapter_result.get("continuity_notes", []) or []:
                    clean_note = str(note or "").strip()
                    if clean_note and clean_note not in continuity:
                        continuity.append(clean_note)

                for item in chapter_result.get("themes", []) or []:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name") or "").strip()
                    if not name:
                        continue
                    key = unicodedata.normalize("NFC", name).casefold()
                    entry = themes_by_key.setdefault(key, {"name": name, "observations": []})
                    entry["observations"].append({
                        "chapter": number, "chapter_title": title,
                        "interpretation": str(item.get("interpretation") or ""),
                        "confidence": _numeric_score(item.get("confidence", 0.0)),
                        "evidence": item.get("evidence"),
                    })

                for item in chapter_result.get("emotional_beats", []) or []:
                    if isinstance(item, dict):
                        emotional_arc.append({
                            **item, "chapter": number, "chapter_title": title,
                        })

                for item in chapter_result.get("character_observations", []) or []:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("character") or "").strip()
                    if not name:
                        continue
                    key = unicodedata.normalize("NFC", name).casefold()
                    arc = character_arcs.setdefault(key, {"character": name, "observations": []})
                    arc["observations"].append({
                        "chapter": number, "chapter_title": title,
                        "motivation": str(item.get("motivation") or ""),
                        "goal": str(item.get("goal") or ""),
                        "change": str(item.get("change") or ""),
                        "confidence": _numeric_score(item.get("confidence", 0.0)),
                        "evidence": item.get("evidence"),
                    })

                for item in chapter_result.get("relationships", []) or []:
                    if isinstance(item, dict):
                        relationship_rows.append({**item, "chapter": number, "chapter_title": title})
                for item in chapter_result.get("key_events", []) or []:
                    if isinstance(item, dict):
                        key_events.append({**item, "chapter": number, "chapter_title": title})

            return {
                "version": 1,
                "analysis_schema_version": 3,
                "book_bible": bible,
                "chapters": results,
                "chapter_summaries": chapter_summaries,
                "book_themes": list(themes_by_key.values()),
                "emotional_arc": emotional_arc,
                "character_arcs": {
                    value["character"]: value for value in character_arcs.values()
                },
                "relationships": relationship_rows,
                "key_events": key_events,
                "pronunciation": aggregate_pronunciation(),
                "continuity_notes": continuity,
                "learning_scope": str(base_context.get("learning_scope") or ""),
            }

        for idx, chapter in enumerate(chapters, 1):
            def chapter_progress(message: str, idx=idx):
                if progress:
                    match = re.search(r"excerpt (\d+)/(\d+)", message)
                    if match:
                        excerpt_index = int(match.group(1))
                        excerpt_total = max(1, int(match.group(2)))
                        fraction = ((idx - 1) + ((excerpt_index - 1) / excerpt_total)) / max(1, len(chapters))
                    else:
                        fraction = (idx - 1) / max(1, len(chapters))
                    progress(max(0.0, min(0.999, fraction)), message)

            book_context = dict(base_context)
            # Later chapters see the accumulated character bible, but never
            # let a supplied context replace the active book's actual cast.
            book_context["characters"] = list(bible.values())
            item = self.analyze_chapter(chapter, book_context, progress=chapter_progress)
            results.append(item)

            for char in item.get("characters", []) or []:
                if not isinstance(char, dict):
                    continue
                name = str(char.get("name", "")).strip()
                if name:
                    entry = bible.setdefault(name, dict(char))
                    if entry is not char:
                        for field in ("aliases", "traits"):
                            old_values = entry.get(field) if isinstance(entry.get(field), list) else []
                            new_values = char.get(field) if isinstance(char.get(field), list) else []
                            merged = list(dict.fromkeys(
                                str(value).strip()
                                for value in [*old_values, *new_values]
                                if str(value or "").strip()
                            ))
                            if merged:
                                entry[field] = merged[:12]
                        if _numeric_score(char.get("confidence", 0.0)) > _numeric_score(entry.get("confidence", 0.0)):
                            for field in ("role", "voice_direction", "confidence"):
                                if field in char:
                                    entry[field] = char[field]

            for candidate in item.get("pronunciation", []) or []:
                if not isinstance(candidate, dict):
                    continue
                written = unicodedata.normalize(
                    "NFC", str(candidate.get("written") or candidate.get("written_form") or "")
                ).strip()
                spoken = unicodedata.normalize(
                    "NFC", str(candidate.get("spoken") or candidate.get("spoken_form") or "")
                ).strip()
                if not written or not spoken:
                    continue
                key = written.casefold()
                occurrence = {
                    "chapter": int(item.get("chapter") or getattr(chapter, "number", idx)),
                    "chapter_title": str(item.get("title") or getattr(chapter, "title", "")),
                }
                current = pronunciation_by_key.get(key)
                if current is None:
                    current = dict(candidate)
                    current["written"] = written
                    current["spoken"] = spoken
                    current["occurrences"] = [occurrence]
                    current["alternatives"] = list(dict.fromkeys(
                        str(value).strip()
                        for value in (candidate.get("alternatives") or [])
                        if str(value or "").strip()
                    ))[:4]
                    pronunciation_by_key[key] = current
                else:
                    occurrences = current.setdefault("occurrences", [])
                    if occurrence not in occurrences:
                        occurrences.append(occurrence)
                    if spoken.casefold() != str(current.get("spoken") or "").casefold():
                        alternatives = current.setdefault("alternatives", [])
                        if spoken not in alternatives and len(alternatives) < 4:
                            alternatives.append(spoken)
                        current["ambiguous_across_chapters"] = True
                    try:
                        new_confidence = float(candidate.get("confidence") or 0.0)
                        old_confidence = float(current.get("confidence") or 0.0)
                    except (TypeError, ValueError, OverflowError):
                        new_confidence, old_confidence = 0.0, 0.0
                    if new_confidence > old_confidence:
                        for field in (
                            "spoken", "ipa", "source_language", "script",
                            "reason", "confidence",
                        ):
                            if field in candidate:
                                current[field] = candidate[field]
                    if current.get("ambiguous_across_chapters"):
                        current["reason"] = (
                            str(current.get("reason") or "").strip()
                            + " Conflicting readings were found across chapters; review the alternatives."
                        ).strip()

            self._save_book(build_report())
            if progress:
                progress(
                    idx / max(1, len(chapters)),
                    f"Completed chapter {idx}/{len(chapters)} • {chapter.title}",
                )

        return build_report()

    def _chunks(self, text: str) -> list[str]:
        # Use a sliding window with real overlap so entities, dialogue tags,
        # scene transitions, and emotional beats at excerpt boundaries retain
        # enough preceding context for the next local inference pass.
        window = max(1, int(self.config.context_chars))
        overlap = min(max(0, int(self.config.overlap_chars)), window - 1)
        stride = window - overlap
        if len(text) <= window:
            return [text]
        out: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + window)
            out.append(text[start:end])
            if end >= len(text):
                break
            start += stride
        return out

    @staticmethod
    def _numeric_intensity(value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        text = str(value or '').strip().casefold()
        mapping = {
            'none': 0.0,
            'very low': 0.15, 'low': 0.25,
            'light': 0.25, 'soft': 0.25,
            'moderate': 0.5, 'medium': 0.5,
            'high': 0.75, 'strong': 0.75,
            'very high': 0.9, 'intense': 0.9,
        }
        if text in mapping:
            return mapping[text]
        try:
            return max(0.0, min(1.0, float(text)))
        except (TypeError, ValueError):
            return 0.0
    def _merge_scenes(self, out: dict[str, Any], data: dict[str, Any]) -> None:
        for raw in data.get('scenes', []) or []:
            if not isinstance(raw, dict):
                continue

            direction_payload = raw.get('narrator_direction')
            if not isinstance(direction_payload, dict):
                direction_payload = {}

            nested_music = raw.get('music')
            nested_music = nested_music if isinstance(nested_music, dict) else {}
            music_style = nested_music.get('style') or raw.get('music_style', '')
            music_intensity = (
                nested_music.get('intensity')
                if nested_music.get('intensity') is not None
                else raw.get('music_intensity', 0.0)
            )

            ambience_payload = raw.get('ambience')
            ambience = ambience_payload if isinstance(ambience_payload, list) else []
            sfx_payload = raw.get('sfx')
            sfx = sfx_payload if isinstance(sfx_payload, list) else []

            scene_record = {
                'summary': str(raw.get('summary', '')).strip(),
                'location': str(raw.get('location', '')).strip(),
                'time': str(raw.get('time', '')).strip(),
                'mood': str(raw.get('mood', 'neutral')).strip() or 'neutral',
                'narrator_direction': {
                    'pace': str(direction_payload.get('pace', raw.get('pace', 'natural'))).strip() or 'natural',
                    'energy': str(direction_payload.get('energy', raw.get('energy', 'medium'))).strip() or 'medium',
                    'delivery': str(direction_payload.get('delivery', raw.get('delivery', ''))).strip(),
                },
                'ambience': [str(value).strip() for value in ambience if str(value).strip()][:3],
                'music': {
                    'style': str(music_style).strip() or None,
                    'intensity': self._numeric_intensity(music_intensity),
                },
                'sfx': [str(value).strip() for value in sfx if str(value).strip()][:4],
                'confidence': _numeric_score(raw.get('confidence', 0.0)),
            }
            out['scenes'].append(scene_record)

        for note in data.get('continuity_notes', []) or []:
            note = str(note).strip()
            if note and note not in out['continuity_notes']:
                out['continuity_notes'].append(note)

    def _merge(self, out: dict[str, Any], data: dict[str, Any], seen: set[str], source_text: str = '') -> None:
        for character in data.get('characters', []) or []:
            if not isinstance(character, dict):
                continue
            item = dict(character)
            item['confidence'] = _numeric_score(item.get('confidence', 0.0))
            out['characters'].append(item)

        for scene in data.get('scenes', []) or []:
            if not isinstance(scene, dict):
                continue
            item = dict(scene)
            item['confidence'] = _numeric_score(item.get('confidence', 0.0))
            out['scenes'].append(item)

        existing_pronunciations = {
            str(item.get('written', '')).casefold(): item
            for item in out.get('pronunciation', [])
            if str(item.get('written', '')).strip()
        }
        for item in data.get('pronunciation', []) or []:
            if not isinstance(item, dict):
                continue
            normalized = _normalise_pronunciation(item, source_text)
            if normalized is None:
                continue
            key = normalized['written'].casefold()
            previous = existing_pronunciations.get(key)
            if previous is None or normalized['confidence'] > float(previous.get('confidence', 0.0) or 0.0):
                existing_pronunciations[key] = normalized
        out['pronunciation'] = list(existing_pronunciations.values())
        for item in data.get('dialogue', []) or []:
            if not isinstance(item, dict):
                continue
            quote = str(item.get('quote', '')).strip()
            if quote and quote.casefold() not in seen:
                normalized_dialogue = dict(item)
                normalized_dialogue['confidence'] = _numeric_score(item.get('confidence', 0.0))
                out['dialogue'].append(normalized_dialogue)
                seen.add(quote.casefold())
        for note in data.get('continuity_notes', []) or []:
            if note not in out['continuity_notes']:
                out['continuity_notes'].append(note)

    def _save_chapter(self, data: dict[str, Any]) -> None:
        path = self.analysis_dir / f"chapter_{int(data['chapter']):04d}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def _save_book(self, data: dict[str, Any]) -> None:
        self.output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')