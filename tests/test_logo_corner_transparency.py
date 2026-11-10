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

    def test_white_square_matte_connected_to_all_edges_is_removed(self):
        clean_logo = _load_logo_cleanup()
        image = Image.new("RGBA", (200, 200), (248, 248, 248, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 191, 191), radius=44, fill=(54, 3, 18, 255))
        # Light book pages and gold/ivory artwork stay because they are
        # enclosed by the red logo and do not connect to the outer matte.
        draw.rectangle((80, 88, 120, 112), fill=(245, 238, 208, 255))
        draw.rectangle((94, 76, 106, 84), fill=(252, 220, 142, 255))

        result = clean_logo(image)
        for point in ((100, 1), (1, 100), (198, 100), (100, 198)):
            self.assertEqual(result.getpixel(point)[3], 0, f"White square matte remained at {point}")
        self.assertEqual(result.getpixel((100, 100))[3], 255)
        self.assertEqual(result.getpixel((100, 80))[3], 255)
        self.assertEqual(result.getpixel((100, 50))[3], 255)

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

    def test_cleanup_flood_fills_boundary_matte_and_legacy_corner_pads(self):
        source = BUILD_SOURCE.read_text(encoding="utf-8")
        self.assertIn("ImageDraw.floodfill(connected_background", source)
        self.assertIn("for x in range(width):", source)
        self.assertIn("for y in range(height):", source)
        self.assertIn("corner = max(12, round(min(width, height) * 0.14))", source)
        self.assertIn("matte = connected_background.point", source)
        self.assertIn("ImageChops.subtract(rgba.getchannel(\"A\"), matte)", source)


if __name__ == "__main__":
    unittest.main()
