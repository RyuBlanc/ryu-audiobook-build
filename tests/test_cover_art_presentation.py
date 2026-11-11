from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CoverArtPresentationTests(unittest.TestCase):
    def test_brand_watermark_is_limited_to_empty_cover_placeholders(self):
        html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        self.assertIn(
            '.book-cover:not(.has-project-cover):after{content:"RYU',
            html,
            "The Ryu brand mark belongs only on the fallback placeholder.",
        )
        self.assertNotIn(
            '.book-cover:after{content:"RYU',
            html,
            "A global pseudo-element would watermark user-selected cover artwork.",
        )

    def test_project_cover_renderer_toggles_placeholder_state_without_editing_image(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("element.classList.add('has-project-cover')", adapter)
        self.assertIn("element.classList.remove('has-project-cover')", adapter)
        self.assertIn("element.style.backgroundImage = 'url", adapter)
        self.assertIn("element.style.removeProperty('background-image')", adapter)


if __name__ == "__main__":
    unittest.main()
