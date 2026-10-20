"""Keep the required limitation ledger synchronized with the real adapter/capability map."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIMITATIONS = ROOT / "KNOWN_LIMITATIONS.md"
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"


class KnownLimitationsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = LIMITATIONS.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.host = HOST.read_text(encoding="utf-8")

    def test_required_limitations_are_documented(self):
        for phrase in (
            "project.create",
            "performance.info",
            "secure provider-specific credential store",
            "Premium cloud candidate generation",
            "Review status is persisted in `chapters.json`",
            "Per-line AI speaker suggestions are still prototype-only",
            "Dialogue-line speaker assignment is not persisted by the current backend",
            "Custom project-library and audio-assets root selection is not implemented",
            "Per-model actions",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.casefold(), self.doc.casefold())

    def test_documented_capability_gaps_match_source(self):
        self.assertIn('"project.create": False', self.host)
        self.assertIn('"performance.info": False', self.host)
        self.assertIn('"diagnostics.export_logs": self._diagnostics_export_logs', self.host)
        self.assertIn('"diagnostics.export_logs": True', self.host)
        self.assertIn("call('diagnostics.export_logs')", self.adapter)
        self.assertIn("Sanitized log export", self.doc)
        self.assertIn('"chapter.review": self._chapter_review', self.host)
        self.assertIn('"chapter.review": True', self.host)
        self.assertIn("call('chapter.review'", self.adapter)
        for phrase in (
            "Credential management is not connected to a secure provider-specific credential store",
            "Premium cloud candidate generation is not connected to a provider endpoint",
            "Per-line AI speaker suggestions are still prototype-only",
            "Custom project-library and audio-assets root selection is not implemented",
            "Dialogue-line speaker assignment is not persisted by the current backend",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.adapter)

    def test_document_does_not_claim_manual_acceptance_from_ci(self):
        self.assertIn("CI does not replace interactive Windows acceptance", self.doc)
        self.assertIn("remain pending", self.doc)
        self.assertIn("Do not describe Stage 8.2.11 as fully accepted", self.doc)


if __name__ == "__main__":
    unittest.main()
