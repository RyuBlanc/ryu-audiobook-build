from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "installer" / "html_installer.py"


def _source_nodes():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    return source, ast.parse(source)


def _load_geometry_helper():
    _source, tree = _source_nodes()
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_installer_window_geometry"
    )
    module = ast.Module(body=[helper], type_ignores=[])
    namespace = {}
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace)
    return namespace["_installer_window_geometry"]


def _load_fit_script() -> str:
    _source, tree = _source_nodes()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "INSTALLER_VIEWPORT_FIT_JS"
               for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("Installer viewport-fit script is missing.")


class InstallerWindowDisplayTests(unittest.TestCase):
    def test_default_display_is_centered_and_uses_target_setup_size(self):
        geometry = _load_geometry_helper()
        self.assertEqual(geometry((0, 0, 1920, 1080)), (370, 160, 1180, 760))

    def test_window_adapts_to_common_laptop_display(self):
        geometry = _load_geometry_helper()
        self.assertEqual(geometry((0, 0, 1366, 768)), (93, 23, 1180, 721))

    def test_window_never_exceeds_small_available_screen(self):
        geometry = _load_geometry_helper()
        x, y, width, height = geometry((0, 0, 800, 600))
        self.assertEqual((x, y, width, height), (16, 18, 768, 564))
        self.assertLessEqual(width, 800)
        self.assertLessEqual(height, 600)

    def test_fit_script_prevents_page_scrollbars_without_scaling_down_text(self):
        script = _load_fit_script()
        self.assertIn("html.style.overflow = \"hidden\"", script)
        self.assertIn("body.style.overflow = \"hidden\"", script)
        self.assertIn("overflow:hidden!important", script)
        self.assertIn('body.style.padding = "8px"', script)
        self.assertIn('wizard.style.minHeight = "0"', script)
        self.assertIn('wizard.style.maxHeight = "100%"', script)
        self.assertIn(".sidebar,.screens{scrollbar-width:none}", script)
        self.assertNotIn("transform", script)
        self.assertNotIn("scale(", script)

    def test_fit_script_has_valid_javascript_syntax_when_node_is_available(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not available in this test environment.")
        script = _load_fit_script()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "installer_viewport_fit.js"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_user_resizing_has_reasonable_responsive_minimums(self):
        source, _tree = _source_nodes()
        self.assertIn("min(900, window_width)", source)
        self.assertIn("min(560, window_height)", source)


    def test_window_supports_native_resize_and_refits_after_resize(self):
        source, _tree = _source_nodes()
        self.assertIn("def _resize_edges_at", source)
        self.assertIn("handle.startSystemResize(edges)", source)
        self.assertIn("Qt.CursorShape.SizeFDiagCursor", source)
        self.assertIn("QTimer.singleShot(60, self._fit_page_to_viewport)", source)


    def test_html_keeps_all_installer_details_and_footer_inside_compact_frame(self):
        html = (ROOT / "installer" / "ryu_installer.html").read_text(encoding="utf-8")
        self.assertIn("height:min(720px,100%)", html)
        self.assertIn("min-height:0;max-height:100%", html)
        self.assertNotIn("min-height:620px", html)
        self.assertIn(".sidebar{min-width:0;min-height:0;overflow-y:auto", html)
        self.assertIn(".screens{flex:1 1 auto;min-height:0;position:relative;overflow:auto", html)
        self.assertIn(".footer{min-height:68px;flex:0 0 auto", html)
        self.assertIn("@media(max-height:700px)", html)
        self.assertIn("@media(max-height:620px)", html)
        self.assertNotIn(".sidebar{display:none}", html)
        for control_id in ("cancel", "back", "next", "topMinimize", "topClose"):
            self.assertIn(f'id="{control_id}"', html)
        self.assertIn('id="quote"', html) if 'id="quote"' in html else self.assertIn(
            "A new way to experience every story.", html
        )
        self.assertIn('id="versionLabel"', html)

    def test_browser_zoom_shortcuts_are_intercepted_by_native_window(self):
        source, _tree = _source_nodes()
        self.assertIn("self.web.setZoomFactor(1.0)", source)
        self.assertIn("Qt.Key.Key_Plus", source)
        self.assertIn("Qt.Key.Key_Minus", source)
        self.assertIn("Qt.KeyboardModifier.ControlModifier", source)
        self.assertIn("event_type == QEvent.Type.Wheel", source)


if __name__ == "__main__":
    unittest.main()
