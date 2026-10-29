# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_localization.py
# Module Type: Automated tests
# Purpose: Verify English fallback and future locale resource behavior.
# Responsibilities: Missing locales, malformed overrides and GUI catalog merging.
# Author: Rudolf Klusal
# License: MIT

"""Translation fallback tests using small independent resource directories."""

import json
import ast
import re
import tempfile
import unittest
from pathlib import Path

from scr_tools.localization.translator import Translator


PUBLIC_COPY_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:movement|mover|moving|jiggl\w*)\b|"
    r"\bmouse\s+mov\w*\b|\bCtrl\s*\+\s*Shift\s*\+\s*S\b",
    re.IGNORECASE,
)


class LocalizationTests(unittest.TestCase):
    """Check safe rendering when optional translations are absent or damaged."""

    def test_shipped_english_catalog_has_core_messages(self) -> None:
        """The English domain catalog supplies meaningful user-facing text."""
        translator: Translator = Translator()
        for key in (
            "configuration.damaged", "movement.completed",
            "capture.failed", "hotkey.invalid",
        ):
            self.assertTrue(translator.has_key(key))
            self.assertNotEqual(translator.text(key), key)

    def test_all_literal_application_keys_have_english_fallbacks(self) -> None:
        """Every literal domain, native, and GUI message key has a resource."""
        source_root: Path = Path(__file__).resolve().parents[1] / "src"
        translator: Translator = Translator()
        key_pattern: re.Pattern[str] = re.compile(
            r"(?:app|button|capture|configuration|error|hotkey|language|"
            r"movement|native|settings|status|tab|tray)\.[a-z_]+"
        )
        missing: set[str] = set()
        for source in source_root.rglob("*.py"):
            tree: ast.Module = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    # This dotted literal is a filename, not a message key.
                    and node.value != "settings.json"
                    and key_pattern.fullmatch(node.value)
                    and not translator.has_key(node.value)
                ):
                    missing.add(node.value)
        self.assertEqual(missing, set())

    def test_missing_locale_uses_english(self) -> None:
        """Unsupported locale identifiers do not break the interface."""
        self.assertEqual(
            Translator("sv").text("movement.completed"),
            Translator("en").text("movement.completed"),
        )

    def test_catalog_copy_uses_public_product_vocabulary(self) -> None:
        """Captions, hints and failures follow the same public copy contract."""
        directory: Path = (
            Path(__file__).resolve().parents[1]
            / "src" / "scr_tools" / "localization"
        )
        for path in sorted(directory.glob("*.json")):
            catalog: dict[str, str] = json.loads(path.read_text("utf-8"))
            for key, message in catalog.items():
                with self.subTest(catalog=path.name, key=key):
                    self.assertNotRegex(message, PUBLIC_COPY_PATTERN)

    def test_distribution_documents_follow_public_copy_contract(self) -> None:
        """Readme, contributor notes and shipped previews use approved copy."""
        root: Path = Path(__file__).resolve().parents[1]
        paths: list[Path] = [root / "README.md", root / "AGENTS.md"]
        paths.extend(sorted((root / "docs").rglob("*.md")))
        paths.extend(sorted((root / "docs").rglob("*.html")))
        for path in paths:
            with self.subTest(document=path.relative_to(root).as_posix()):
                self.assertNotRegex(path.read_text("utf-8"), PUBLIC_COPY_PATTERN)

    def test_partial_and_malformed_locale_fallback(self) -> None:
        """Broken optional entries fall back independently to their English text."""
        with tempfile.TemporaryDirectory() as temporary:
            directory: Path = Path(temporary)
            (directory / "en.json").write_text(json.dumps({
                "hello": "Hello {name}", "missing": "English fallback",
            }), encoding="utf-8")
            (directory / "en.gui.json").write_text('{"gui": "Open"}', encoding="utf-8")
            (directory / "sv.json").write_text(json.dumps({
                "hello": "Hej {wrong_parameter}", "ignored": 123,
            }), encoding="utf-8")
            translator: Translator = Translator("sv", directory)
            self.assertEqual(translator.text("hello", name="Rudolf"), "Hello Rudolf")
            self.assertEqual(translator.text("missing"), "English fallback")
            self.assertEqual(translator.text("gui"), "Open")
            self.assertEqual(translator.text("unknown"), "unknown")

    def test_languages_are_discovered_from_base_resources(self) -> None:
        """New resource files add language choices without editing GUI code."""
        with tempfile.TemporaryDirectory() as temporary:
            directory: Path = Path(temporary)
            (directory / "en.json").write_text(
                '{"language.display_name": "English"}', encoding="utf-8"
            )
            (directory / "sv.json").write_text(
                '{"language.display_name": "Svenska"}', encoding="utf-8"
            )
            (directory / "de.json").write_text('{}', encoding="utf-8")
            (directory / "sv.gui.json").write_text('{}', encoding="utf-8")
            languages: dict[str, str] = Translator("en", directory).available_languages()
            self.assertEqual(languages, {"en": "English", "de": "de", "sv": "Svenska"})


if __name__ == "__main__":
    unittest.main()
