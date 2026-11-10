from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TaskManagerResponsiveStylesTests(unittest.TestCase):
    def test_task_manager_and_job_details_use_viewport_bounded_widths(self):
        source = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        helper_start = source.index("function ensureTaskManagerResponsiveStyles()")
        helper_end = source.index("\n  let narratorOnlySavePromise", helper_start)
        helper = source[helper_start:helper_end]

        self.assertIn("#backgroundJobsModal .jobs-modal", helper)
        self.assertIn(".modal-back .jobs-modal", helper)
        self.assertIn("width:min(780px,calc(100vw - 40px))!important", helper)
        self.assertIn("width:min(760px,calc(100vw - 40px))!important", helper)
        self.assertIn("#jobDetailsModal .modal", helper)
        self.assertIn("max-width:calc(100vw - 40px)!important", helper)
        self.assertIn("min-width:0!important", helper)
        self.assertIn("grid-template-columns:repeat(auto-fit,minmax(min(210px,100%),1fr))!important", helper)
        self.assertIn("@media(max-width:640px)", helper)
        self.assertIn("ensureTaskManagerResponsiveStyles();", source[:helper_start + len(helper) + 200])

    def test_job_details_modal_css_is_injected_before_lazy_task_manager_or_model_views(self):
        source = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        startup_call = source.index("ensureTaskManagerResponsiveStyles();")
        model_inventory = source.index("function renderModelInventory()")
        dynamic_modal = source.index("function ensureJobDetailsModal()")
        self.assertLess(startup_call, model_inventory)
        self.assertLess(startup_call, dynamic_modal)
        self.assertIn("style.id = 'ryuTaskManagerResponsiveStyles'", source)

    def test_dynamic_job_details_inline_width_is_overridden_by_bounded_rule(self):
        source = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('style="width:min(760px,calc(100vw - 28px));max-height:calc(100vh - 36px);overflow:auto"', source)
        helper = source[source.index("function ensureTaskManagerResponsiveStyles()"):source.index("\n  let narratorOnlySavePromise")]
        self.assertIn("!important", helper)
        self.assertIn("#jobDetailsModal .modal", helper)


if __name__ == "__main__":
    unittest.main()
