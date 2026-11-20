"""Regressions for application-wide Premium V2 select popovers."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StableSelectPopoverContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = (
            ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")

    def _helper(self):
        start = self.adapter.index("function installStableSelectPopovers()")
        end = self.adapter.index("function setProductionStatus(", start)
        return self.adapter[start:end]

    def test_shared_select_popover_is_installed_before_backend_hydration(self):
        start = self.adapter.index("async function wire()")
        end = self.adapter.index("\n  }", start)
        wire = self.adapter[start:end]
        self.assertIn("installStableSelectPopovers();", wire)
        self.assertLess(
            wire.index("installStableSelectPopovers();"),
            wire.index("await call('app.get_info')"),
        )

    def test_original_select_remains_the_value_source_and_dispatches_change(self):
        helper = self._helper()
        self.assertIn("select.selectedIndex = index;", helper)
        self.assertIn("new Event('input', {bubbles: true})", helper)
        self.assertIn("new Event('change', {bubbles: true})", helper)
        self.assertIn("select.dispatchEvent(", helper)
        self.assertIn("activeSelect = null;", helper)

    def test_popover_supports_pointer_keyboard_and_escape_interaction(self):
        helper = self._helper()
        for required in (
            "pointerdown",
            "ArrowDown",
            "ArrowUp",
            "Home",
            "End",
            "PageDown",
            "PageUp",
            "Escape",
            "Enter",
            "aria-expanded",
            "aria-activedescendant",
        ):
            self.assertIn(required, helper)

    def test_dynamic_selects_and_option_updates_are_observed(self):
        helper = self._helper()
        self.assertIn("new MutationObserver", helper)
        self.assertIn("record.addedNodes.forEach(collectSelects)", helper)
        self.assertIn("renderPopoverOptions()", helper)
        self.assertIn("activeSelect.isConnected", helper)

    def test_disabled_options_and_non_dropdown_selects_keep_native_semantics(self):
        helper = self._helper()
        self.assertIn("!select.multiple", helper)
        self.assertIn("Number(select.size || 0) <= 1", helper)
        self.assertIn("option.disabled !== true", helper)
        self.assertIn("activeSelect.disabled", helper)


if __name__ == "__main__":
    unittest.main()
