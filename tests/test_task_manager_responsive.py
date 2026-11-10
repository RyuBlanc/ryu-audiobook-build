from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TaskManagerResponsiveStylesTests(unittest.TestCase):
    def test_task_manager_width_rule_uses_parent_constraint_and_is_installed_at_startup(self):
        source = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        helper_start = source.index("function ensureTaskManagerResponsiveStyles()")
        helper_end = source.index("\n  let narratorOnlySavePromise", helper_start)
        helper = source[helper_start:helper_end]

        self.assertIn("#backgroundJobsModal .jobs-modal", helper)
        self.assertIn(".modal-back .jobs-modal", helper)
        self.assertIn("width:min(780px,100%)!important", helper)
        self.assertNotIn("100vw", helper)
        self.assertIn("max-width:100%!important", helper)
        self.assertIn("min-width:0!important", helper)
        self.assertIn("margin-left:auto", helper)
        self.assertIn("margin-right:auto", helper)
        self.assertIn("ensureTaskManagerResponsiveStyles();", source[:helper_start + len(helper) + 200])

    def test_task_manager_width_does_not_depend_on_opening_models_center(self):
        source = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        startup_call = source.index("ensureTaskManagerResponsiveStyles();")
        model_inventory = source.index("function renderModelInventory()")
        self.assertLess(startup_call, model_inventory)
        self.assertIn("style.id = 'ryuTaskManagerResponsiveStyles'", source)


if __name__ == "__main__":
    unittest.main()
