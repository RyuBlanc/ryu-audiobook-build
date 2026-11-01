"""Release version contract for Ryu's Audiobook."""
import unittest

from app.version import APP_NAME, APP_VERSION, RELEASE_LABEL, full_version


class ApplicationVersionContractTests(unittest.TestCase):
    def test_application_uses_requested_stable_baseline(self):
        self.assertEqual(APP_NAME, "Ryu's Audiobook")
        self.assertEqual(APP_VERSION, "1.1.1")
        self.assertTrue(RELEASE_LABEL.startswith("v1.1.1 • Build "))
        self.assertEqual(full_version(), RELEASE_LABEL)

    def test_version_has_three_numeric_components(self):
        components = APP_VERSION.split(".")
        self.assertEqual(len(components), 3)
        self.assertTrue(all(component.isdigit() for component in components))


if __name__ == "__main__":
    unittest.main()
