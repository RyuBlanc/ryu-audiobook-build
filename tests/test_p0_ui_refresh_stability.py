"""P0 UI regression checks for flicker-free background job progress updates."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BackgroundJobRefreshStabilityTests(unittest.TestCase):
    def test_progress_text_is_updated_in_place_not_used_to_rebuild_job_rows(self):
        adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("async function refreshJobsImpl()")
        end = adapter.index("async function monitorJob(", start)
        refresh = adapter[start:end]
        signature_start = refresh.index("const signature = jobs.map")
        signature_end = refresh.index("if (box.dataset.backendJobsSignature !== signature)", signature_start)
        signature = refresh[signature_start:signature_end]

        self.assertIn("j.job_id, j.state, j.type, j.title, Boolean(j.recoverable)", signature)
        self.assertNotIn("Boolean(j.message)", signature)
        self.assertNotIn("Boolean(j.error?.message)", signature)
        self.assertIn("if (box && panelVisible)", refresh)
        self.assertIn("messageNode.textContent = j.message || ''", refresh)
        self.assertIn("errorNode.textContent = j.error?.message || ''", refresh)
        self.assertIn("if (progress) progress.style.width = pct + '%';", refresh)


if __name__ == "__main__":
    unittest.main()
