from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_character_worker_uses_existing_book_wide_local_ai_pipeline():
    host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
    start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
    end = host.index("\n    def _character_assign(", start)
    worker = host[start:end]
    assert "from app.ai.brain import AudiobookBrain" in worker
    assert "brain.analyze_book(" in worker
    assert "progress=update_ai_progress" in worker
    assert "brain.close()" in worker
    assert "source_grounded_fallback" in worker


def test_ai_dialogue_predictions_are_grounded_in_the_exact_chapter_source_and_cast():
    host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
    assert "ai_dialogue_by_chapter" in host
    assert "quote_key not in source_key" in host
    assert "Local AI book-context analysis:" in host
    assert "canonical_speaker" in host


def test_analysis_reports_full_coverage_and_no_silent_suggestion_limit():
    host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
    start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
    end = host.index("\n    def _character_assign(", start)
    worker = host[start:end]
    assert "max_suggestions = 3000" not in worker
    assert '"processed_chapters": processed_chapters' in worker
    assert '"total_chapters": total_chapters' in worker
    assert '"coverage_complete":' in worker
    assert '"truncated": False' in worker


def test_local_ai_book_context_starts_with_the_user_saved_character_cast():
    brain = (ROOT / "app/ai/brain.py").read_text(encoding="utf-8")
    assert 'initial_characters = base_context.get("characters")' in brain
    assert 'bible[name] = dict(row, name=name)' in brain
    assert 'book_context["characters"] = list(bible.values())' in brain
