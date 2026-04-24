"""Unit tests for differ.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from differ import (
    ChangeType,
    compile_ignore_patterns,
    diff,
    extract_structure,
    fingerprint,
    normalise,
)


class NormaliseTests(unittest.TestCase):
    def test_ignore_patterns_strip_tokens(self) -> None:
        patterns = compile_ignore_patterns([
            r'csrf_token["\s:=]+[A-Za-z0-9]+',
            r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b',
        ])
        raw = 'welkom csrf_token=ABC123 op 2024-01-02T03:04:05Z hallo'
        result = normalise(raw, patterns)
        self.assertNotIn("csrf_token", result)
        self.assertNotIn("2024-01-02T03:04:05Z", result)
        self.assertIn("welkom", result)
        self.assertIn("hallo", result)

    def test_invalid_pattern_is_skipped(self) -> None:
        patterns = compile_ignore_patterns(["[unclosed", r"\d+"])
        self.assertEqual(len(patterns), 1)
        self.assertEqual(normalise("abc 123 def", patterns), "abc  def")


class StructureTests(unittest.TestCase):
    def test_structure_ignores_text_content(self) -> None:
        a = "<html><body><h1>Oud</h1><p class='lead'>hallo</p></body></html>"
        b = "<html><body><h1>Nieuw</h1><p class='lead'>wereld</p></body></html>"
        self.assertEqual(extract_structure(a), extract_structure(b))

    def test_structure_detects_new_tag(self) -> None:
        a = "<html><body><p>a</p></body></html>"
        b = "<html><body><p>a</p><p>b</p></body></html>"
        self.assertNotEqual(extract_structure(a), extract_structure(b))

    def test_structure_detects_class_change(self) -> None:
        a = "<html><body><div class='old'>x</div></body></html>"
        b = "<html><body><div class='new'>x</div></body></html>"
        self.assertNotEqual(extract_structure(a), extract_structure(b))

    def test_class_order_does_not_matter(self) -> None:
        a = "<html><body><div class='alpha beta'>x</div></body></html>"
        b = "<html><body><div class='beta alpha'>x</div></body></html>"
        self.assertEqual(extract_structure(a), extract_structure(b))


class DiffTests(unittest.TestCase):
    def _fp(self, url: str, text: str, html: str):
        return fingerprint(url, text, html, "2026-04-24T00:00:00+00:00", [])

    def test_new_page(self) -> None:
        before = {}
        after = {"https://afas.nl/a": self._fp("https://afas.nl/a", "hi", "<html><p>hi</p></html>")}
        report = diff(before, after)
        self.assertEqual(len(report.changes), 1)
        self.assertEqual(report.changes[0].change_type, ChangeType.NEW)

    def test_removed_page(self) -> None:
        before = {"https://afas.nl/a": self._fp("https://afas.nl/a", "hi", "<html><p>hi</p></html>")}
        after = {}
        report = diff(before, after)
        self.assertEqual(len(report.changes), 1)
        self.assertEqual(report.changes[0].change_type, ChangeType.REMOVED)

    def test_text_changed(self) -> None:
        url = "https://afas.nl/a"
        before = {url: self._fp(url, "hallo", "<html><body><p>hallo</p></body></html>")}
        after = {url: self._fp(url, "hallo wereld", "<html><body><p>hallo wereld</p></body></html>")}
        report = diff(before, after)
        types = [c.change_type for c in report.changes]
        self.assertIn(ChangeType.TEXT_CHANGED, types)
        self.assertNotIn(ChangeType.STRUCTURE_CHANGED, types)

    def test_structure_only_change(self) -> None:
        url = "https://afas.nl/a"
        before = {url: self._fp(url, "zelfde tekst", "<html><body><p>zelfde tekst</p></body></html>")}
        after = {url: self._fp(url, "zelfde tekst",
                               "<html><body><div><p>zelfde tekst</p></div></body></html>")}
        report = diff(before, after)
        types = [c.change_type for c in report.changes]
        self.assertIn(ChangeType.STRUCTURE_CHANGED, types)
        self.assertNotIn(ChangeType.TEXT_CHANGED, types)

    def test_no_change(self) -> None:
        url = "https://afas.nl/a"
        html = "<html><body><p>zelfde</p></body></html>"
        before = {url: self._fp(url, "zelfde", html)}
        after = {url: self._fp(url, "zelfde", html)}
        report = diff(before, after)
        self.assertEqual(report.changes, [])

    def test_dynamic_tokens_ignored_via_patterns(self) -> None:
        url = "https://afas.nl/a"
        patterns = compile_ignore_patterns([r'csrf_token=\w+'])
        before_text = "welkom csrf_token=AAA111 einde"
        after_text = "welkom csrf_token=BBB222 einde"
        html = "<html><body>x</body></html>"
        before = {url: fingerprint(url, before_text, html, "t", patterns)}
        after = {url: fingerprint(url, after_text, html, "t", patterns)}
        self.assertEqual(diff(before, after).changes, [])


if __name__ == "__main__":
    unittest.main()
