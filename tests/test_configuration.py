# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_configuration.py
# Module Type: Automated tests
# Purpose: Verify preference validation and durable JSON recovery behavior.
# Responsibilities: Defaults, persistence, invalid fields and forward compatibility.
# Author: Rudolf Klusal
# License: MIT

"""Behavioral tests for complete persisted configuration snapshots."""

import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from scr_tools.configuration import (
    ConfigurationError, ConfigurationStore, FutureSchemaError, Settings,
    validate_settings,
)
from scr_tools.core.hotkey_spec import parse_hotkey


class ConfigurationTests(unittest.TestCase):
    """Exercise disk persistence and externally observable validation behavior."""

    def setUp(self) -> None:
        """Create isolated temporary settings and screenshot directories."""
        self.temporary: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.directory: Path = Path(self.temporary.name)
        self.path: Path = self.directory / "profile" / "settings.json"
        self.store: ConfigurationStore = ConfigurationStore(
            self.path, self.directory / "Pictures" / "SCR Tools"
        )

    def tearDown(self) -> None:
        """Remove only this test's temporary files."""
        self.temporary.cleanup()

    def test_required_defaults(self) -> None:
        """A new install uses the specified noninteractive default behavior."""
        settings: Settings = self.store.load()
        self.assertEqual(settings.idle_seconds, 100)
        self.assertTrue(settings.mover_enabled)
        self.assertTrue(settings.prevent_sleep)
        self.assertFalse(settings.keep_displays_awake)
        self.assertEqual(settings.pattern, "rectangle")
        self.assertEqual(settings.distance_pixels, 30)
        self.assertEqual(settings.duration_seconds, 1.0)
        self.assertEqual(settings.screenshot_mode, "all")
        self.assertEqual(settings.screenshot_hotkey, "Ctrl+Shift+F11")
        self.assertFalse(settings.start_minimized)
        self.assertFalse(settings.start_with_windows)
        self.assertFalse(self.path.exists())

    def test_settings_survive_new_store(self) -> None:
        """Every schema field survives an atomic write and a simulated restart."""
        expected: Settings = replace(
            self.store.load(), idle_seconds=321, mover_enabled=False,
            pattern="circle", distance_pixels=61, duration_seconds=2.3,
            prevent_sleep=False, keep_displays_awake=True,
            screenshot_hotkey="Alt+Ctrl+F9", screenshot_mode="each",
            start_minimized=True, start_with_windows=True, language="sv",
        )
        self.store.save(expected)
        restored: Settings = ConfigurationStore(self.path, self.directory).load()
        self.assertEqual(restored, replace(expected, screenshot_hotkey="Ctrl+Alt+F9"))
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_damaged_json_is_preserved(self) -> None:
        """Corrupt JSON yields defaults and preserves original bytes in backup."""
        self.path.parent.mkdir()
        original: str = '{"idle_seconds": '
        self.path.write_text(original, encoding="utf-8")
        self.assertEqual(self.store.load().idle_seconds, 100)
        backups: list[Path] = list(self.path.parent.glob("settings.json.broken.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), original)
        self.assertIn("configuration.damaged", self.store.notices)

    def test_future_schema_cannot_be_overwritten(self) -> None:
        """A newer schema is read conservatively without destroying unknown data."""
        self.path.parent.mkdir()
        original: str = '{"schema_version": 8, "idle_seconds": 250, "future": {"x": 1}}'
        self.path.write_text(original, encoding="utf-8")
        loaded: Settings = self.store.load()
        self.assertEqual(loaded.idle_seconds, 250)
        self.assertTrue(self.store.read_only)
        with self.assertRaises(FutureSchemaError):
            self.store.save(loaded)
        self.assertEqual(self.path.read_text(encoding="utf-8"), original)

    def test_invalid_fields_do_not_discard_valid_fields(self) -> None:
        """Malformed individual values reset independently from valid preferences."""
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({
            "schema_version": 1, "idle_seconds": True, "distance_pixels": 50,
            "mover_enabled": "yes", "duration_seconds": float("nan"),
            "screenshot_folder": "relative/folder", "start_minimized": True,
        }), encoding="utf-8")
        loaded: Settings = self.store.load()
        self.assertEqual(loaded.idle_seconds, 100)
        self.assertEqual(loaded.distance_pixels, 50)
        self.assertEqual(loaded.duration_seconds, 1.0)
        self.assertTrue(loaded.mover_enabled)
        self.assertTrue(loaded.start_minimized)
        self.assertIn("configuration.fields_reset", self.store.notices)

    def test_bounds_and_nonfinite_values_are_rejected(self) -> None:
        """Nonfinite durations, bool integers and out-of-range limits never save."""
        defaults: Settings = self.store.load()
        candidates: list[Settings] = [
            replace(defaults, idle_seconds=9),
            replace(defaults, idle_seconds=86_401),
            replace(defaults, distance_pixels=0),
            replace(defaults, duration_seconds=float("inf")),
            replace(defaults, duration_seconds=float("nan")),
            replace(defaults, screenshot_folder="C:relative"),
            replace(defaults, screenshot_folder="C:\\bad?name"),
            replace(defaults, screenshot_hotkey="F11"),
        ]
        for candidate in candidates:
            with self.subTest(candidate=asdict(candidate)):
                with self.assertRaises(ConfigurationError):
                    validate_settings(candidate)

    def test_unversioned_data_is_migrated(self) -> None:
        """An initial unversioned settings object receives the current schema."""
        self.path.parent.mkdir()
        self.path.write_text('{"idle_seconds": 180}', encoding="utf-8")
        loaded: Settings = self.store.load()
        self.assertEqual(loaded.schema_version, 1)
        self.assertEqual(loaded.idle_seconds, 180)
        self.assertIn("configuration.migrated", self.store.notices)

    def test_hotkey_parser_flags_and_reserved_key(self) -> None:
        """Shortcut flags are native values and F12/duplicate modifiers fail."""
        shortcut = parse_hotkey("shift + control + f11")
        self.assertEqual(shortcut.label, "Ctrl+Shift+F11")
        self.assertEqual(shortcut.modifiers, 0x0002 | 0x0004)
        self.assertEqual(shortcut.key_code, 0x7A)
        for invalid in ("Ctrl+F12", "Ctrl+Ctrl+A", "Ctrl++A", "Ctrl+A+B"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_hotkey(invalid)


if __name__ == "__main__":
    unittest.main()
