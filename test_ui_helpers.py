#!/usr/bin/env python3
"""Tests for modern UI helper utilities."""
import unittest

from ui import nav, primitives


class DummyFont:
    def __init__(self, char_width=6):
        self.char_width = char_width

    def size(self, text):
        return (len(text) * self.char_width, 10)


class TestUiHelpers(unittest.TestCase):
    def test_nav_hit_test_bounds(self):
        self.assertEqual(nav.nav_hit_test(5, 235), "home")
        self.assertEqual(nav.nav_hit_test(85, 235), "library")
        self.assertEqual(nav.nav_hit_test(165, 235), "stats")
        self.assertEqual(nav.nav_hit_test(245, 235), "settings")
        self.assertIsNone(nav.nav_hit_test(160, 50))

    def test_elide_text_no_change(self):
        font = DummyFont(char_width=6)
        text = "short"
        self.assertEqual(primitives.elide_text(text, 60, font), text)

    def test_elide_text_truncates(self):
        font = DummyFont(char_width=6)
        text = "very-long-name"
        elided = primitives.elide_text(text, 30, font)
        self.assertTrue(elided.endswith("…"))
        self.assertLessEqual(font.size(elided)[0], 30)


if __name__ == '__main__':
    unittest.main()
