from __future__ import annotations

import ast
from pathlib import Path
import unittest

from PIL import Image, ImageChops, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
BUILD_SOURCE = ROOT / "build.py"


def _load_logo_cleanup():
    source = BUILD_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_remove_outer_neutral_logo_halo"
    )
    module = ast.Module(body=[helper], type_ignores=[])
    namespace = {"Image": Image, "ImageChops": ImageChops, "ImageDraw": ImageDraw}
    exec(compile(module, str(BUILD_SOURCE), "exec"), namespace)
    return namespace[helper.name]


class LogoCornerTransparencyTests(unittest.TestCase):
    def test_pale_square_pads_are_removed_from_all_four_corners(self):
        clean_logo = _load_logo_cleanup()
        image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # These 10x10 patches sit 8–13% in from each corner, matching the
        # opaque pale pads visible outside the rounded logo tile.
        for box in (
            (17, 17, 26, 26),
            (173, 17, 182, 26),
            (17, 173, 26, 182),
            (173, 173, 182, 182),
        ):
            draw.rectangle(box, fill=(245, 245, 245, 255))

        result = clean_logo(image)
        for point in ((21, 21), (178, 21), (21, 178), (178, 178)):
            self.assertEqual(result.getpixel(point)[3], 0, f"Corner pad remained at {point}")

    def test_legitimate_center_art_and_edge_accents_are_preserved(self):
        clean_logo = _load_logo_cleanup()
        image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((85, 85, 115, 115), fill=(245, 238, 208, 255))
        draw.rectangle((4, 92, 12, 108), fill=(245, 245, 245, 255))
        draw.rectangle((18, 18, 27, 27), fill=(225, 25, 45, 255))

        result = clean_logo(image)
        self.assertEqual(result.getpixel((100, 100))[3], 255)
        self.assertEqual(result.getpixel((8, 100))[3], 255)
        self.assertEqual(result.getpixel((22, 22))[3], 255)

    def test_corner_cleanup_is_limited_to_the_outer_fourteen_percent(self):
        source = BUILD_SOURCE.read_text(encoding="utf-8")
        self.assertIn("corner = max(12, round(min(width, height) * 0.14))", source)
        self.assertIn("corners = Image.new(\"L\", rgba.size, 0)", source)
        self.assertNotIn("min(width, height) * 0.06", source)


if __name__ == "__main__":
    unittest.main()
