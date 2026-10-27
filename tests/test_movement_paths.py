# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_movement_paths.py
# Module Type: Automated tests
# Purpose: Verify physical-pixel closed paths across monitor arrangements.
# Responsibilities: Edge containment, negative coordinates and true path shapes.
# Author: Rudolf Klusal
# License: MIT

"""Geometry tests for physical monitor bounds and uninterrupted path closure."""

import unittest

from scr_tools.core.movement_paths import Bounds, Point, generate_path


class MovementPathTests(unittest.TestCase):
    """Exercise real geometry invariants rather than snapshotting implementation."""

    def test_edges_corners_and_negative_monitors(self) -> None:
        """Every path stays inside its starting monitor and closes exactly."""
        monitors: list[Bounds] = [
            (0, 0, 1920, 1080), (-2560, -240, 0, 1200),
            (100, -1440, 2660, 0), (-5, -5, 5, 5),
        ]
        for bounds in monitors:
            left, top, right, bottom = bounds
            starts: list[Point] = [
                (left, top), (right - 1, bottom - 1),
                (left, bottom - 1), (right - 1, top),
                ((left + right) // 2, (top + bottom) // 2),
            ]
            for pattern in ("rectangle", "circle"):
                for start in starts:
                    for size in (1, 30, 1000):
                        with self.subTest(bounds=bounds, start=start, pattern=pattern, size=size):
                            path: list[Point] = generate_path(pattern, start, bounds, size)
                            self.assertEqual(path[0], start)
                            self.assertEqual(path[-1], start)
                            self.assertEqual(len(path), 61)
                            self.assertTrue(any(point != start for point in path))
                            for x, y in path:
                                self.assertTrue(left <= x < right)
                                self.assertTrue(top <= y < bottom)

    def test_paths_have_real_two_dimensional_extent(self) -> None:
        """Standard rectangle and circle paths contain many animated positions."""
        for pattern in ("rectangle", "circle"):
            path: list[Point] = generate_path(pattern, (100, 100), (0, 0, 500, 500), 30)
            self.assertGreater(len(set(path)), 20)
            self.assertEqual(max(x for x, _y in path) - min(x for x, _y in path), 30)
            self.assertEqual(max(y for _x, y in path) - min(y for _x, y in path), 30)

    def test_invalid_start_and_pattern_are_rejected(self) -> None:
        """Bad geometry cannot silently move on another display."""
        with self.assertRaises(ValueError):
            generate_path("rectangle", (100, 100), (0, 0, 100, 100), 30)
        with self.assertRaises(ValueError):
            generate_path("unknown", (20, 20), (0, 0, 100, 100), 30)


if __name__ == "__main__":
    unittest.main()
