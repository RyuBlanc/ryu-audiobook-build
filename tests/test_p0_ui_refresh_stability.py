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


    def test_premium_effects_bound_blur_and_disable_whole_view_entry_animations(self):
        html = (
            ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
        ).read_text(encoding="utf-8")
        start = html.index("Release stability: reduce repeated whole-view paints")
        end = html.index("</style>", start)
        head_end = html.lower().index("</head>")
        guard = html[start:end]
        self.assertLess(start, head_end)
        self.assertGreaterEqual(start, html.rfind("<style>", 0, head_end))
        self.assertIn(".page.active", guard)
        self.assertIn("#voices>.content", guard)
        self.assertIn("#voices .panel.active", guard)
        self.assertIn(".char-view.active", guard)
        self.assertIn(".sound-view.active", guard)
        self.assertIn("animation:none!important", guard)
        self.assertIn("transform:none!important", guard)
        self.assertIn("backdrop-filter:blur(10px) saturate(125%)!important", guard)
        self.assertIn("backdrop-filter:blur(6px) saturate(115%)!important", guard)
        self.assertIn("backdrop-filter:blur(12px) saturate(125%)!important", guard)
        # High-effects mode also caps the unbounded workflow/loader blur layers;
        # users must not need to enable the Reduce Motion accessibility option.
        self.assertIn("html[data-effects='high'] .workflow,", guard)
        self.assertIn("html[data-effects='high'] .loader-glass", guard)
        self.assertIn("backdrop-filter:blur(8px) saturate(120%)!important", guard)
        self.assertIn("html[data-effects='normal'] .workflow", guard)
        self.assertIn("backdrop-filter:blur(5px) saturate(110%)!important", guard)
        self.assertIn("html[data-effects='normal'] .loader-glass", guard)
        self.assertIn("backdrop-filter:blur(4px) saturate(110%)!important", guard)
        self.assertIn("animation:none!important", guard)
        self.assertIn("transform:none!important", guard)
        self.assertIn(".production-flow{", guard)
        self.assertIn("backdrop-filter:none!important", guard)
        self.assertIn("@media(min-width:1181px) and (max-width:1366px)", guard)
        self.assertIn(".flow-track{", guard)
        self.assertIn("overflow-x:auto!important", guard)
        self.assertIn(".flow-stage{flex:0 0 132px!important}", guard)



if __name__ == "__main__":
    unittest.main()
