from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PremiumV2ImportStatusContractTests(unittest.TestCase):
    def test_import_worker_persists_and_project_removal_clears_latest_import(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('"import.latest.get": self._import_latest_get', host)
        self.assertIn("record_latest_import(project)", host)
        self.assertIn("clear_latest_import_for_folder(target)", host)
        self.assertIn("def _import_latest_get", host)

    def test_premium_v2_import_page_renders_recent_import_and_open_action(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function refreshLatestImport()", adapter)
        self.assertIn("call('import.latest.get')", adapter)
        self.assertIn("latestImportCard", adapter)
        self.assertIn("data-open-latest-import", adapter)
        self.assertIn("call('project.open', {folder:record.project_folder})", adapter)
        self.assertIn("await refreshLatestImport()", adapter)


if __name__ == "__main__":
    unittest.main()
