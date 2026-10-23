"""Stage 6 installer branding and user-data preservation contract tests."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "RyuAudiobook.iss"


class InstallerBrandingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = INSTALLER.read_text(encoding="utf-8")

    def test_setup_wizard_uses_premium_v2_dark_gold_palette(self):
        # Native Inno Setup dark styling keeps standard controls (checkboxes,
        # summary memos, dialogs and buttons) readable; test the new UI contract
        # rather than requiring the old label-only color overrides.
        self.assertIn("WizardStyle=modern dark hidebevels includetitlebar", self.script)
        self.assertIn("WizardBackColor=#05060A", self.script)
        self.assertIn("WizardImageFile=..\\assets\\installer_brand_panel.bmp", self.script)
        self.assertIn("WizardImageBackColor=#05060A", self.script)
        self.assertIn("WizardSmallImageFile=..\\assets\\ryu_audiobook_logo.bmp", self.script)
        self.assertIn("WizardSmallImageBackColor=#05060A", self.script)
        self.assertIn("DefaultDialogFontName=Segoe UI", self.script)
        self.assertIn("SetupIconFile=..\\assets\\ryu_audiobook_logo.ico", self.script)
        self.assertNotIn("WizardForm.Color :=", self.script)
        self.assertNotIn("WizardForm.InnerPage.Color :=", self.script)

    def test_logo_render_keeps_native_resolution_and_original_transparency(self):
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("source_size = renderer.defaultSize()", build_script)
        self.assertIn("roundedBrandTile", build_script)
        self.assertIn("ImageChops.multiply(alpha, clip_mask)", build_script)
        self.assertIn("mask_scale = 4", build_script)
        self.assertIn("Image.Resampling.LANCZOS", build_script)
        self.assertIn("required_ico_sizes", build_script)
        self.assertIn("icon_file.ico.sizes()", build_script)
        self.assertIn("icon_file.ico.getimage(icon_size)", build_script)
        self.assertIn("missing_sizes = required_ico_sizes - icon_sizes", build_script)
        self.assertIn("alpha_min > 16", build_script)
        self.assertIn("alpha_max < 128", build_script)
        self.assertIn("visible_pixels < pixel_count * 0.20", build_script)
        self.assertIn("alpha_histogram = icon_alpha.histogram()", build_script)
        self.assertIn("icon_alpha.getextrema()", build_script)
        self.assertIn("Application logo canvas corners must remain fully transparent.", build_script)
        logo_svg = (ROOT / "assets" / "ryu_audiobook_logo.svg").read_text(encoding="utf-8")
        self.assertNotIn("removeWhiteMatte", logo_svg)
        self.assertIn('clip-path="url(#roundedBrandTile)"', logo_svg)
        self.assertNotIn("QImage(1024, 1024", build_script)

        # The main window and legacy Import control must prefer the PNG asset,
        # retaining SVG only as a source-checkout fallback.
        for relative_path in ("app/main.py", "app/ui/workflow.py"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertLess(
                source.index("ryu_audiobook_logo.png"),
                source.index("ryu_audiobook_logo.svg"),
            )

    def test_setup_keeps_standard_install_launch_and_shortcut_paths(self):
        self.assertIn('DefaultDirName={autopf}\\Ryu\'s Audiobook', self.script)
        self.assertIn('#define MyAppExeName "Ryu\'s Audiobook.exe"', self.script)
        self.assertIn('Filename: "{app}\\{#MyAppExeName}"', self.script)
        self.assertIn('Flags: nowait postinstall skipifsilent', self.script)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"', self.script)

    def test_uninstaller_does_not_delete_user_data(self):
        self.assertIn("User books, voices, models, and settings live under %USERPROFILE%", self.script)
        self.assertIn("[UninstallDelete]", self.script)
        self.assertIn("Deliberately do not remove user data outside {app}.", self.script)
        self.assertNotIn("Type: filesandordirs; Name: \"{userprofile}", self.script)



    def test_inno_uses_dark_composited_bitmaps_without_flattening_application_art(self):
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn('LOGO_MASTER_PNG = ASSETS / "ryu_audiobook_logo_master.png"', build_script)
        self.assertIn("with Image.open(LOGO_MASTER_PNG) as source", build_script)
        self.assertIn('LOGO_BMP = ASSETS / "ryu_audiobook_logo.bmp"', build_script)
        self.assertIn('INSTALLER_BRAND_PANEL_BMP = ASSETS / "installer_brand_panel.bmp"', build_script)
        self.assertIn("rgba.save(LOGO_PNG, format=\"PNG\", optimize=True)", build_script)
        self.assertIn("logo_backdrop = Image.new(\"RGB\", rgba.size, (5, 6, 10))", build_script)
        self.assertIn("panel_bitmap = Image.new(\"RGB\", panel.size, (5, 6, 10))", build_script)


    def test_html_installer_builder_validates_distribution_as_directory(self):
        builder = (ROOT / "installer" / "build_html_installer.py").read_text(encoding="utf-8")
        self.assertIn("if not APP_DIST.is_dir():", builder)
        self.assertIn("for path in (APP_EXE, CORE_INSTALLER, HTML, HTML_JS, LOGO_PNG, LOGO_ICO):", builder)
        self.assertNotIn("for path in (APP_DIST, APP_EXE, CORE_INSTALLER", builder)
        self.assertIn("if not package_files:", builder)
        self.assertIn("if APP_EXE not in package_files:", builder)


    def test_html_installer_controls_are_wired_before_startup(self):
        html = (ROOT / "installer" / "ryu_installer.html").read_text(encoding="utf-8")
        js = (ROOT / "installer" / "ryu_installer.js").read_text(encoding="utf-8")
        bridge = (ROOT / "installer" / "html_installer.py").read_text(encoding="utf-8")
        self.assertIn('id="topMinimize"', html)
        self.assertIn('id="topClose"', html)
        self.assertIn('id="browse"', html)
        self.assertIn('id="confirmExit"', html)
        self.assertIn('id="packageFiles"', html)
        self.assertIn("const minimizeButton=$('topMinimize');if(minimizeButton)", js)
        self.assertNotIn("$('topMinimize').onclick=", js)
        self.assertIn("$('browse').onclick=browseDirectory", js)
        self.assertIn("$('confirmExit').onclick=", js)
        self.assertIn("environmentChecked&&Number(environment.free_space_bytes)>0", js)
        self.assertIn("Number(info.file_count||0).toLocaleString()", js)
        self.assertIn("app.installEventFilter(window)", bridge)
        self.assertIn("handle.startSystemMove()", bridge)
        self.assertIn("QFileDialog.getExistingDirectory", bridge)

    def test_logo_pipeline_clears_only_the_outer_neutral_halo(self):
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("def _remove_outer_neutral_logo_halo(image: Image.Image)", build_script)
        self.assertIn("band = max(12, round(min(width, height) * 0.06))", build_script)
        self.assertIn("rgba = _remove_outer_neutral_logo_halo(rgba)", build_script)
        self.assertIn("ImageChops.subtract(rgba.getchannel(\"A\"), halo)", build_script)


    def test_html_setup_bridge_runs_the_actual_windows_installer(self):
        html = (ROOT / "installer" / "ryu_installer.html").read_text(encoding="utf-8")
        html_js = (ROOT / "installer" / "ryu_installer.js").read_text(encoding="utf-8")
        bridge = (ROOT / "installer" / "html_installer.py").read_text(encoding="utf-8")
        builder = (ROOT / "installer" / "build_html_installer.py").read_text(encoding="utf-8")
        self.assertIn("qrc:///qtwebchannel/qwebchannel.js", html)
        self.assertIn('src="ryu_installer.js"', html)
        self.assertIn("bridge.startInstall(JSON.stringify(payload)", html_js)
        self.assertNotIn("progress=Math.min(100,progress+", html_js)
        self.assertIn("ShellExecuteExW", bridge)
        self.assertIn("/VERYSILENT", bridge)
        self.assertIn("getEnvironmentForPath", bridge)
        self.assertIn("--onefile", builder)
        self.assertIn("ryu_installer.js", builder)
        self.assertIn("Ryu's Audiobook Core Setup.exe", builder)



    def test_html_installer_uses_generated_full_resolution_logo_not_embedded_preview(self):
        html = (ROOT / "installer" / "ryu_installer.html").read_text(encoding="utf-8")
        builder = (ROOT / "installer" / "build_html_installer.py").read_text(encoding="utf-8")
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        self.assertIn('src="../assets/ryu_audiobook_logo.png"', html)
        self.assertNotIn('src="data:image/png;base64,', html)
        self.assertIn('f"--add-data={LOGO_PNG};assets"', builder)
        self.assertIn("candidate.width >= 1200 and candidate.height >= 1200", build_script)
        self.assertIn("QSvgRenderer(str(LOGO_SVG))", build_script)
        self.assertIn("ryu-audiobook-windows-build-${{ github.ref }}", workflow)
        core_compile_at = workflow.index("- name: Build core installer payload")
        restore_python_at = workflow.index("- name: Restore Python for HTML installer packaging")
        html_package_at = workflow.index("- name: Build functional HTML installer")
        verify_assets_at = workflow.index("- name: Verify original logo transparency and generate release hashes")
        self.assertLess(core_compile_at, restore_python_at)
        self.assertLess(restore_python_at, html_package_at)
        self.assertLess(html_package_at, verify_assets_at)
        self.assertIn("id: html_python", workflow)
        self.assertIn("HTML_PYTHON: ${{ steps.html_python.outputs.python-path }}", workflow)
        self.assertIn("$pythonExe = $env:HTML_PYTHON", workflow)
        self.assertIn("ryu-qwen-python-bootstrap\\python312\\python.exe", workflow)
        self.assertIn("$pythonExe -m ensurepip --upgrade", workflow)
        self.assertIn("$env:PYTHONPATH = (Get-Location).Path", workflow)
        self.assertIn("- name: Validate installer JavaScript syntax", workflow)
        self.assertIn("--check 'installer\\ryu_installer.js'", workflow)

if __name__ == "__main__":
    unittest.main()
