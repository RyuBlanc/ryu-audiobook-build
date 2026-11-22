from __future__ import annotations

"""Character-only, source-grounded local literary cast extraction."""

import json
import re
import unicodedata
import time
from pathlib import Path
from typing import Any, Callable

from app.ai.model_runtime import BrainRuntimeError, LocalLLM
from app.chapters.characters import (
    _clean_name,
    _discover_candidates,
    _discover_explicit_speakers,
    _identity_key,
    is_likely_character_name,
)
from app.chapters.detector import Chapter

CHARACTER_CAST_VERSION = "1.0.0"
CANDIDATE_BATCH_SIZE = 24
MAX_CONTEXTS_PER_CANDIDATE = 3
_ALLOWED_KINDS = {
    "speaker_label", "dialogue_attribution", "self_introduction",
    "named_action", "named_person_reference", "honorific_reference",
}

CHARACTER_ONLY_PROMPT = """You are Ryu Audiobook Studio's conservative literary CHARACTER CAST EXTRACTOR.
Your ONLY task is to identify actual named characters in the supplied novel excerpts and candidate inventory.

SOURCE TYPES YOU MUST HANDLE
- Japanese light novels and web novels: Japanese script, translated English editions, romaji, honorifics such as -san, -sama, -kun, -chan, senpai and sensei, plus 「」 and 『』 dialogue.
- English novels: fantasy, romance, mystery, science fiction, web fiction, classics and translated fiction.
- Chinese: Simplified/Traditional Han characters and romanisation.
- Korean: Hangul and romanisation.
- South Asian languages/scripts: Devanagari, Tamil, Telugu, Bengali, Gujarati, Gurmukhi, Malayalam, Kannada, Marathi, Urdu and others when present in source text.
- Other languages and scripts: preserve exact Unicode spelling and use source evidence; never invent transliterations.

A CHARACTER IS a distinct named in-story individual: person, animal, named intelligent creature, spirit, deity, robot/AI, or personified being. Include main, supporting and minor named individuals only when the story establishes them as individuals.

NEVER RETURN
- Book, novel, series, volume or chapter titles; table-of-contents text; author, translator, publisher, website, filenames, watermarks or metadata.
- Places, countries, cities, schools, academies, guilds, clans, factions, organisations, ships, shops, buildings or groups unless the text clearly personifies one as an individual.
- Objects, weapons, artefacts, spells, skills, abilities, foods, events, species, ranks, jobs, generic titles or epithets unless clearly used as the name of a distinct individual.
- Pronouns, articles, interjections, sentence starters, ordinary capitalised words, descriptive phrases or generic role labels.
- Anything that appears only in a heading/title or is guessed from genre familiarity.
- Any name not present in the provided candidate inventory.

STRICT EVIDENCE REQUIREMENTS
1. Choose only exact names from candidate_inventory. Do not invent, repair, complete or add names.
2. Every returned character must have at least one exact contiguous quote from a supplied source_evidence excerpt. That quote must contain the name and show it is an individual in the story.
3. Prefer explicit speaker labels, dialogue attributions, self-introductions, named actions and clear references to a person. A bare mention, heading or location reference is not enough.
4. A title, place, organisation, item or ability does not become a character because it is capitalised or repeated.
5. Do not split a Japanese/Korean/Chinese name into multiple characters because of honorifics. Keep the canonical name without the honorific when source evidence supports that form.
6. Merge aliases only when the source explicitly links both spellings to the same individual. Never guess an alias from similar spelling.
7. Confidence is not evidence. If unsure, omit the candidate.
8. Return no dialogue mapping, chapter summary, scenes, themes, relationships, pronunciation, locations, music, SFX, or general analysis.

CALIBRATION EXAMPLES (fictional; learn the distinction)
- English: “Mira introduced herself. ‘I am Mira,’ she said.” -> Mira is a character. “The Silver Tower guarded the valley.” -> Silver Tower is a place, not a character.
- Japanese light-novel style: “Akari-san entered. ‘I am Akari,’ she said.” -> Akari is one character; san is an honorific, not another name. “Volume 2: The Azure Academy” -> heading/place, not a character.
- Chinese: “李明先生走进房间，李明向大家问好。” -> 李明 may be an individual when the source identifies the person.
- Korean: “민수: ‘어서 와.’” -> 민수 is a character when used as a speaker label.
- Hindi: “मीरा: ‘मैं यहाँ हूँ।’” -> मीरा is a character when used as a speaker label.
- Tamil: “கவிதா: ‘வணக்கம்।’” -> கவிதா is a character when used as a speaker label.
- “The Reborn Dragon” as a novel heading is not a character. A named dragon who speaks and acts as an individual may be.

OUTPUT EXACTLY ONE JSON OBJECT
{"characters":[{"name":"exact source spelling","aliases":[],"role":"main|supporting|minor|unknown","confidence":0.0,"evidence":[{"chapter":1,"kind":"speaker_label|dialogue_attribution|self_introduction|named_action|named_person_reference|honorific_reference","quote":"exact contiguous source text"}]}]}
Return {"characters":[]} when no character is proven. JSON only; no markdown or explanation."""

_HONORIFIC_PATTERNS = (
    re.compile(r"(?P<name>[\u3040-\u30ff\u3400-\u9fff]{2,12})(?=(?:さん|ちゃん|くん|君|様|さま|先輩|先生|氏))"),
    re.compile(r"(?P<name>[\uac00-\ud7af]{2,8})(?=(?:씨|님|선배|형|오빠|언니|누나))"),
    re.compile(r"(?P<name>[\u4e00-\u9fff]{2,6})(?=(?:先生|小姐|同学|老師|老师|女士|殿下|公子|姑娘))"),
    re.compile(r"(?P<name>[\u0900-\u097f]{2,24})(?=(?:जी|साहब))"),
    re.compile(r"(?P<name>[\u0b80-\u0bff]{2,24})(?=(?:அவர்கள்|அய்யா|அம்மா))"),
    re.compile(r"(?P<name>[\u0c00-\u0c7f]{2,24})(?=(?:గారు|అయ్యా|అమ్మా))"),
    re.compile(r"(?P<name>[\u0980-\u09ff]{2,24})(?=(?:দা|দি|বাবু|মশাই))"),
    re.compile(r"(?P<name>[\u0a00-\u0a7f]{2,24})(?=(?:ਜੀ|ਸਾਹਿਬ))"),
    re.compile(r"(?P<name>[\u0a80-\u0aff]{2,24})(?=(?:જી|સાહેબ))"),
)
_LATIN_HONORIFIC = re.compile(r"(?i)(?:[-\s]+)(san|sama|kun|chan|senpai|sensei)$")


def _key(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def _clean_candidate(value: Any) -> str:
    name = _clean_name(str(value or ""))
    name = _LATIN_HONORIFIC.sub("", name).strip()
    return _clean_name(name)


def _contains(source: str, value: str) -> bool:
    needle = _key(value)
    return bool(needle) and needle in _key(source)


def _parse_json(raw: str) -> dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", str(raw or ""), flags=re.I | re.S).strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^\s*" + re.escape(fence) + r"(?:json)?\s*|\s*" + re.escape(fence) + r"\s*$", "", text, flags=re.I | re.S).strip()
    start = text.find("{")
    if start < 0:
        raise BrainRuntimeError("Character-only analyzer returned no JSON object.")
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise BrainRuntimeError(f"Character-only analyzer returned malformed JSON: {exc.msg}.") from exc
    if not isinstance(value, dict):
        raise BrainRuntimeError("Character-only analyzer returned a non-object result.")
    return value


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _heading_line(line: str, title_keys: set[str]) -> bool:
    clean = str(line or "").strip().strip("#*_~ ")
    key = _key(clean)
    if not key:
        return False
    if key in title_keys:
        return True
    heading = re.sub(
        r"^(?:chapter|ch\.?|volume|vol\.?|part|book|episode)\s*"
        r"(?:#?\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)?"
        r"\s*[:：\-–—.]*\s*",
        "",
        clean,
        flags=re.I,
    )
    heading_key = _key(heading)
    return heading_key in title_keys if heading_key else False


def _index_candidate_contexts(
    source: str,
    names: set[str],
    chapter: int,
    title_keys: set[str],
) -> dict[str, dict[str, Any]]:
    """Locate all candidate occurrences in one shared multi-pattern text scan."""
    normalised_chars: list[str] = []
    original_offsets: list[int] = []
    for original_index, original_char in enumerate(source):
        transformed = unicodedata.normalize("NFKC", original_char).casefold()
        for char in transformed:
            if char.isspace():
                if not normalised_chars or normalised_chars[-1] == " ":
                    continue
                char = " "
            normalised_chars.append(char)
            original_offsets.append(original_index)
    while normalised_chars and normalised_chars[0] == " ":
        normalised_chars.pop(0)
        original_offsets.pop(0)
    while normalised_chars and normalised_chars[-1] == " ":
        normalised_chars.pop()
        original_offsets.pop()
    normalised_source = "".join(normalised_chars)

    trie: dict[Any, Any] = {}
    for name in names:
        key = _key(name)
        if not key:
            continue
        node = trie
        for char in key:
            node = node.setdefault(char, {})
        node.setdefault(None, []).append(name)

    indexed: dict[str, dict[str, Any]] = {}
    for start_index, first_char in enumerate(normalised_source):
        node = trie.get(first_char)
        if node is None:
            continue
        end_index = start_index
        while node is not None and end_index < len(normalised_source):
            if end_index > start_index:
                node = node.get(normalised_source[end_index])
            if node is None:
                break
            for name in node.get(None, []):
                original_start = original_offsets[start_index]
                original_end = original_offsets[end_index] + 1
                line_start = source.rfind("\n", 0, original_start) + 1
                line_end = source.find("\n", original_end)
                if line_end < 0:
                    line_end = len(source)
                if _heading_line(source[line_start:line_end], title_keys):
                    continue
                record = indexed.setdefault(_key(name), {"count": 0, "contexts": []})
                record["count"] += 1
                if len(record["contexts"]) >= MAX_CONTEXTS_PER_CANDIDATE:
                    continue
                context_start = max(0, original_start - 115)
                context_end = min(len(source), original_end + 135)
                quote = source[context_start:context_end].strip()
                context_key = _key(quote)
                if quote and all(_key(row["quote"]) != context_key for row in record["contexts"]):
                    record["contexts"].append({"chapter": chapter, "quote": quote})
            end_index += 1
    return indexed

def build_candidate_inventory(
    chapters: list[Chapter],
    metadata_titles: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Extract a source-only whitelist; title headings never count as evidence."""
    title_values = list(metadata_titles or ())
    title_values.extend(str(getattr(chapter, "title", "") or "") for chapter in chapters)
    title_keys = {_key(value) for value in title_values if str(value or "").strip()}
    title_tokens = [value.split() for value in title_keys if value]
    by_key: dict[str, dict[str, Any]] = {}

    for chapter in chapters:
        source = unicodedata.normalize("NFC", str(getattr(chapter, "text", "") or ""))
        if not source.strip():
            continue
        explicit_names = {_clean_candidate(name) for name in _discover_explicit_speakers(source)}
        explicit_names.discard("")
        names = {_clean_candidate(name) for name in _discover_candidates(source)}
        names.update(explicit_names)
        for pattern in _HONORIFIC_PATTERNS:
            names.update(_clean_candidate(match.group("name")) for match in pattern.finditer(source))
        names.discard("")

        number = int(getattr(chapter, "number", 0) or 0)
        context_index = _index_candidate_contexts(source, names, number, title_keys)
        for name in names:
            key = _key(name)
            explicit = key in {_key(value) for value in explicit_names}
            if not is_likely_character_name(name, explicit=explicit):
                continue
            name_words = key.split()
            # Do not seed a multi-word candidate that is itself a phrase from a
            # book/series/volume/chapter title. A character may still be found
            # from independent non-heading evidence elsewhere in the story.
            title_phrase = any(
                any(title_words[index:index + len(name_words)] == name_words
                    for index in range(max(0, len(title_words) - len(name_words) + 1)))
                for title_words in title_tokens
                if name_words
            )
            # A phrase that is part of a supplied work/series/chapter title
            # is never seeded as a character unless the source explicitly tags
            # it as a speaking individual.
            if title_phrase and not explicit:
                continue
            evidence_record = context_index.get(key) or {}
            contexts = evidence_record.get("contexts") or []
            if not contexts:
                continue
            row = by_key.setdefault(key, {
                "name": name,
                "mention_count": 0,
                "chapters": [],
                "explicit_speaker_evidence": False,
                "source_evidence": [],
            })
            row["mention_count"] += int(evidence_record.get("count") or 0)
            row["explicit_speaker_evidence"] = bool(row["explicit_speaker_evidence"] or explicit)
            if number not in row["chapters"]:
                row["chapters"].append(number)
            for context in contexts:
                if context not in row["source_evidence"] and len(row["source_evidence"]) < 8:
                    row["source_evidence"].append(context)

    rows = list(by_key.values())
    rows.sort(key=lambda row: (
        not row["explicit_speaker_evidence"],
        -int(row["mention_count"]),
        -len(row["chapters"]),
        _key(row["name"]),
    ))
    return rows


class CharacterCastAnalyzer:
    """Dedicated model path that returns only verified character suggestions."""

    def __init__(self, project_folder: Path | None = None):
        self.project_folder = project_folder
        self.llm = LocalLLM()

    def close(self) -> None:
        self.llm.close()

    def analyze_book(
        self,
        chapters: list[Chapter],
        *,
        metadata_titles: list[str] | tuple[str, ...] | None = None,
        known_characters: list[dict[str, Any]] | None = None,
        progress: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        model_request_count = 0
        repair_request_count = 0
        sources = {
            int(getattr(chapter, "number", index) or index): unicodedata.normalize(
                "NFC", str(getattr(chapter, "text", "") or "")
            )
            for index, chapter in enumerate(chapters, 1)
        }
        inventory = build_candidate_inventory(chapters, metadata_titles)
        batches = [
            inventory[index:index + CANDIDATE_BATCH_SIZE]
            for index in range(0, len(inventory), CANDIDATE_BATCH_SIZE)
        ]
        accepted: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []

        for batch_number, batch in enumerate(batches, 1):
            if progress:
                progress(
                    (batch_number - 1) / max(1, len(batches)),
                    f"Character-only scan • candidate batch {batch_number}/{len(batches)}",
                )
            known = [
                {
                    "name": str(row.get("name") or "").strip(),
                    "aliases": list(row.get("aliases") or [])[:8]
                    if isinstance(row.get("aliases") or [], (list, tuple)) else [],
                }
                for row in (known_characters or [])
                if isinstance(row, dict) and str(row.get("name") or "").strip()
            ][:80]
            payload = {
                "candidate_inventory": batch,
                "known_user_confirmed_characters": known,
                "metadata_titles_to_exclude": [
                    str(value).strip() for value in (metadata_titles or ()) if str(value or "").strip()
                ][:80],
            }
            request = (
                "Select only proven story characters in candidate_inventory. Every accepted name must "
                "have an exact quote copied from that candidate's source_evidence. Names outside this "
                "batch are forbidden. Return the character-only JSON contract and nothing else.\n"
                + json.dumps(payload, ensure_ascii=False)
            )
            try:
                model_request_count += 1
                raw = self.llm.complete(
                    CHARACTER_ONLY_PROMPT,
                    "/no_think " + request,
                    max_tokens=min(2600, 850 + len(batch) * 65),
                    temperature=0.0,
                )
                data = _parse_json(raw)
            except Exception as first_error:
                # One compact repair only; never restart the whole book scan.
                try:
                    model_request_count += 1
                    repair_request_count += 1
                    raw = self.llm.complete(
                        "Return only valid compact JSON with a characters array. Never add names or evidence.",
                        "/no_think Repair the character-only JSON for this exact candidate inventory. "
                        "Use exact source_evidence quotes; use an empty array when uncertain.\n" + request,
                        max_tokens=min(1700, 650 + len(batch) * 45),
                        temperature=0.0,
                    )
                    data = _parse_json(raw)
                except Exception as repair_error:
                    warnings.append(
                        f"Candidate batch {batch_number}/{len(batches)} fell back to explicit source speaker labels "
                        f"after {type(repair_error).__name__}."
                    )
                    data = self._explicit_fallback(batch)

            for row in self._validate_batch(data, batch, sources, metadata_titles):
                key = _key(row["name"])
                previous = accepted.get(key)
                if previous is None:
                    accepted[key] = row
                else:
                    previous["aliases"] = list(dict.fromkeys([
                        *(previous.get("aliases") or []), *(row.get("aliases") or [])
                    ]))
                    previous["evidence"] = list(dict.fromkeys([
                        *(previous.get("evidence") or []), *(row.get("evidence") or [])
                    ]))[:8]
                    previous["confidence"] = max(previous["confidence"], row["confidence"])

        characters = sorted(
            accepted.values(),
            key=lambda row: (
                {"main": 0, "supporting": 1, "minor": 2, "unknown": 3}.get(row["role"], 4),
                -row["confidence"],
                _key(row["name"]),
            ),
        )
        runtime = {}
        reader = getattr(self.llm, "runtime_info", None)
        if callable(reader):
            try:
                runtime = reader()
            except Exception as exc:
                warnings.append(f"Model identity could not be read: {type(exc).__name__}.")
        if progress:
            progress(0.99, f"Character-only scan complete • {len(characters)} evidence-verified characters")
        elapsed_seconds = max(0.0, time.monotonic() - started_at)
        return {
            "analysis_mode": "character_cast_only_v1",
            "characters": characters,
            "performance": {
                "elapsed_seconds": round(elapsed_seconds, 3),
                "model_request_count": model_request_count,
                "repair_request_count": repair_request_count,
                "candidate_count": len(inventory),
                "candidate_batch_count": len(batches),
            },
            "warnings": warnings,
            "coverage": {
                "processed_chapters": len(chapters),
                "total_chapters": len(chapters),
                "coverage_complete": True,
                "candidate_count": len(inventory),
                "validated_character_count": len(characters),
                "model_batch_count": len(batches),
                "model_request_count": model_request_count,
                "repair_request_count": repair_request_count,
                "elapsed_seconds": round(elapsed_seconds, 3),
                "truncated": False,
            },
            "runtime": runtime,
        }

    @staticmethod
    def _explicit_fallback(batch: list[dict[str, Any]]) -> dict[str, Any]:
        rows = []
        for candidate in batch:
            if not candidate.get("explicit_speaker_evidence"):
                continue
            evidence = next(
                (
                    {
                        "chapter": quote.get("chapter"),
                        "kind": "speaker_label",
                        "quote": quote.get("quote"),
                    }
                    for quote in candidate.get("source_evidence") or []
                    if isinstance(quote, dict)
                    and _contains(str(quote.get("quote") or ""), candidate["name"])
                ),
                None,
            )
            if evidence:
                rows.append({
                    "name": candidate["name"],
                    "aliases": [],
                    "role": "unknown",
                    "confidence": 0.82,
                    "evidence": [evidence],
                })
        return {"characters": rows}

    def _validate_batch(
        self,
        data: dict[str, Any],
        batch: list[dict[str, Any]],
        sources: dict[int, str],
        metadata_titles: list[str] | tuple[str, ...] | None,
    ) -> list[dict[str, Any]]:
        candidates = {_key(row["name"]): row for row in batch}
        title_keys = {_key(value) for value in (metadata_titles or ()) if str(value or "").strip()}
        validated = []
        raw_rows = data.get("characters")
        if not isinstance(raw_rows, list):
            return validated

        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            name = _clean_candidate(raw.get("name") or "")
            key = _key(name)
            candidate = candidates.get(key)
            if candidate is None:
                continue
            explicit = bool(candidate.get("explicit_speaker_evidence"))
            if _key(name) in title_keys and not explicit:
                continue
            if not is_likely_character_name(name, explicit=explicit):
                continue
            confidence = _confidence(raw.get("confidence"))
            if confidence < 0.82:
                continue

            evidence_rows = raw.get("evidence")
            if not isinstance(evidence_rows, list):
                continue
            verified = []
            kinds = set()
            supplied_contexts = [
                str(row.get("quote") or "")
                for row in candidate.get("source_evidence") or []
                if isinstance(row, dict)
            ]
            for evidence in evidence_rows[:8]:
                if not isinstance(evidence, dict):
                    continue
                quote = str(evidence.get("quote") or "").strip()
                if len(quote) < 5 or len(quote) > 700 or not _contains(quote, name):
                    continue
                try:
                    chapter_number = int(evidence.get("chapter") or 0)
                except (TypeError, ValueError, OverflowError):
                    continue
                source = sources.get(chapter_number, "")
                if not source or not _contains(source, quote):
                    continue
                if not any(_contains(context, quote) for context in supplied_contexts):
                    continue
                kind = str(evidence.get("kind") or "").strip().casefold().replace(" ", "_")
                if kind not in _ALLOWED_KINDS:
                    continue
                verified.append({"chapter": chapter_number, "kind": kind, "quote": quote})
                kinds.add(kind)
            if not verified:
                continue

            mention_count = int(candidate.get("mention_count") or 0)
            strong_single = confidence >= 0.93 and kinds.intersection({
                "self_introduction", "dialogue_attribution", "named_action"
            })
            if not explicit and mention_count < 2 and not strong_single:
                continue

            aliases = []
            raw_aliases = raw.get("aliases")
            if isinstance(raw_aliases, list):
                for value in raw_aliases[:8]:
                    alias = _clean_candidate(value)
                    if (
                        not alias or _key(alias) == key
                        or not is_likely_character_name(alias)
                        or not any(_contains(source_text, alias) for source_text in sources.values())
                        or not any(_contains(row["quote"], alias) for row in verified)
                    ):
                        continue
                    aliases.append(alias)
            role = str(raw.get("role") or "unknown").strip().casefold()
            if role not in {"main", "supporting", "minor", "unknown"}:
                role = "unknown"
            validated.append({
                "name": candidate["name"],
                "aliases": list(dict.fromkeys(aliases)),
                "role": role,
                "confidence": confidence,
                "evidence": verified[:5],
                "mention_count": mention_count,
                "chapter_count": len(candidate.get("chapters") or []),
            })
        return validated
