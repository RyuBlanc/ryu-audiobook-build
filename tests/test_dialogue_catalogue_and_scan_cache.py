from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.chapters.dialogue import dialogue_segments
from app.chapters.speaker_segmentation import segment_chapter_speakers
from app.ui import premium_v2_host as host


def test_character_studio_dialogue_rows_use_the_same_source_spans_as_production():
    text = (
        "Mira looked up.\n"
        "“Who are you?” she asked.\n\n"
        "—I am Ren.\n\n"
        "'Then let us go,' Mira replied.\n\n"
        "The room became quiet."
    )
    chapter = Chapter(1, "Opening", text)

    production = [
        (row.start, row.end)
        for row in segment_chapter_speakers(chapter)
        if row.kind != "narration"
    ]
    character_studio = [
        (row.start, row.end)
        for row in dialogue_segments(chapter)
    ]

    assert character_studio == production
    assert len(character_studio) == 3


def test_multi_speaker_saved_assignment_is_visible_and_conflicts_are_not_ranked_as_confirmed():
    text = "“We should leave,” Mira said."
    chapter = Chapter(1, "Opening", text)
    start = text.index("“")
    end = len(text)
    chapter.dialogue_assignments = [{
        "start": start, "end": end, "text": text[start:end],
        "speakers": ["Mira", "Ren"], "source": "manual",
    }]
    rows = dialogue_segments(chapter)
    assert len(rows) == 1
    assert {item[0] for item in rows[0].suggestions}.issuperset({"Mira", "Ren"})

    chapter.dialogue_assignments.append({
        "start": start, "end": end, "text": text[start:end],
        "speakers": ["Tara"], "source": "manual",
    })
    conflicted = dialogue_segments(chapter)
    assert len(conflicted) == 1
    assert conflicted[0].suggested_speaker != "Tara"


def test_models_inventory_refresh_is_cached_and_force_refreshes(monkeypatch):
    bridge = host.PremiumV2Bridge.__new__(host.PremiumV2Bridge)
    builder = Mock(side_effect=[[{"model_id":"qwen"}], [{"model_id":"piper"}]])
    monkeypatch.setattr("app.tts.model_registry.build_inventory", builder)

    first = bridge._models_list({})
    second = bridge._models_list({})
    refreshed = bridge._models_list({"force_refresh": True})

    assert first == second == [{"model_id":"qwen"}]
    assert refreshed == [{"model_id":"piper"}]
    assert builder.call_count == 2


def test_sound_catalog_scan_is_cached_and_import_style_refresh_can_bypass_cache(tmp_path, monkeypatch):
    bridge = host.PremiumV2Bridge.__new__(host.PremiumV2Bridge)
    app_root = tmp_path / "app"
    audio_root = app_root / "Audio Library"
    audio_root.mkdir(parents=True)
    bundled_root = tmp_path / "bundle"
    (bundled_root / "assets" / "starter_audio").mkdir(parents=True)
    monkeypatch.setattr(host, "app_root", lambda: app_root)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundled_root), raising=False)
    first_file = audio_root / "first.wav"
    first_file.write_bytes(b"first")
    monkeypatch.setattr(
        "app.audio.library.metadata_for",
        lambda path: {"role":"music","category":"fantasy","title":Path(path).stem},
    )

    first = bridge._sound_catalog({})
    second_file = audio_root / "second.wav"
    second_file.write_bytes(b"second")
    cached = bridge._sound_catalog({})
    refreshed = bridge._sound_catalog({"force_refresh": True})

    assert len(first) == 1
    assert len(cached) == 1
    assert len(refreshed) == 2
