"""Tests for line chart null-value handling."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.line_chart import (  # noqa: E402
    _value_label_y_px,
    target_label_layout,
    value_label_above,
    y_scale,
)


class LineChartNullValueTests(unittest.TestCase):
    def test_y_scale_ignores_null_values(self) -> None:
        values = [None, None, 63.0, 65.0, 67.0]
        y_px, y_max = y_scale(63.0, values, None)
        self.assertAlmostEqual(y_max, 67.0 * 1.18)
        self.assertGreater(y_px, 0)

    def test_target_label_layout_skips_null_values(self) -> None:
        values = [None, None, 63.0, 65.0, 67.0]
        labels = ["", "", "63", "65", "67"]
        layout = target_label_layout(values, labels, 70.0, None, 481)
        self.assertIn("tag_below", layout)

    def test_value_label_above_uses_nearest_valid_neighbors(self) -> None:
        values = [None, None, 63.0, 65.0, 67.0]
        above = value_label_above(2, 63.0, values, None, 80.0)
        self.assertTrue(above)

    def test_local_minimum_near_bottom_flips_label_above(self) -> None:
        values = [562_000, 12_300_000, 15_200_000, 6_200_000, 87_000_000]
        _, y_max = y_scale(values[0], values, None)
        point_y, _ = y_scale(values[3], values, None)
        ly, above = _value_label_y_px(3, values[3], values, None, y_max)
        self.assertTrue(above)
        self.assertLess(ly, point_y)


if __name__ == "__main__":
    unittest.main()
