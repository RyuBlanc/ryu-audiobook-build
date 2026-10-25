"""Stage 1425 guards against silently mislabelled audiobook export formats."""
from pathlib import Path
import unittest


class Stage1425OutputFormatContractTests(unittest.TestCase):
    def test_generation_only_accepts_the_container_the_assembler_really_exports(self):
        host = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        self.assertIn('if output.suffix.lower() != ".m4b":', host)
        self.assertIn("M4A/MP3 export is not implemented yet", host)
        self.assertIn('output_path = output_path.with_suffix(".m4b")', assembler)


if __name__ == "__main__":
    unittest.main()
