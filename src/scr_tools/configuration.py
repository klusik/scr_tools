# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/configuration.py
# Module Type: Persistent configuration
# Purpose: Load and atomically save versioned, validated user preferences.
# Responsibilities: Defaults, validation, damaged-file recovery and migrations.
# Author: Rudolf Klusal
# License: MIT

"""Typed preferences stored beneath the user's roaming application data."""

import json
import math
import ntpath
import os
import re
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from scr_tools.core.hotkey_spec import canonicalize_hotkey


SCHEMA_VERSION: int = 1
DEFAULT_IDLE_SECONDS: int = 100
MIN_IDLE_SECONDS: int = 10
MAX_IDLE_SECONDS: int = 86_400
MIN_DISTANCE_PIXELS: int = 1
MAX_DISTANCE_PIXELS: int = 1_000
MIN_DURATION_SECONDS: float = 0.2
MAX_DURATION_SECONDS: float = 10.0
MAX_CONFIGURATION_BYTES: int = 128 * 1024

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type MovementPattern = Literal["rectangle", "circle"]
type ScreenshotMode = Literal["all", "current", "each"]


class ConfigurationError(ValueError):
    """A preference violates a documented setting constraint.

    The exception message is a translation key, never a private path.
    """


class FutureSchemaError(ConfigurationError):
    """A newer configuration schema is readable but must not be overwritten."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Complete immutable settings snapshot shared safely with workers.

    Attributes:
        schema_version: Persisted format revision supported by this release.
        idle_seconds: Uninterrupted external-input inactivity before a cycle.
        mover_enabled: Whether automatic movement and sleep requests operate.
        pattern: Closed movement-path name.
        distance_pixels: Requested rectangle side or circle diameter in pixels.
        duration_seconds: Duration of one complete path in seconds.
        prevent_sleep: Request that Windows not sleep from system inactivity.
        keep_displays_awake: Also request that display idle timers stay awake.
        screenshot_hotkey: Canonical RegisterHotKey shortcut.
        screenshot_mode: Combined desktop, pointer monitor, or each monitor.
        screenshot_folder: Absolute output directory, or empty before defaults.
        start_minimized: Start with the main window hidden in the tray.
        start_with_windows: Register the installed executable for user logon.
        language: Locale resource name, with English fallback.
    """

    schema_version: int = SCHEMA_VERSION
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    mover_enabled: bool = True
    pattern: MovementPattern = "rectangle"
    distance_pixels: int = 30
    duration_seconds: float = 1.0
    prevent_sleep: bool = True
    keep_displays_awake: bool = False
    screenshot_hotkey: str = "Ctrl+Shift+F11"
    screenshot_mode: ScreenshotMode = "all"
    screenshot_folder: str = ""
    start_minimized: bool = False
    start_with_windows: bool = False
    language: str = "en"


def _valid_folder(folder: str) -> bool:
    """Check path syntax without accessing storage or requiring existence.

    Args:
        folder: Absolute Windows directory, or a native absolute test path.

    Returns:
        True for a nonempty absolute directory with safe Windows characters.
    """
    if not folder or folder != folder.strip():
        return False
    if any(ord(character) < 32 for character in folder):
        return False
    if any(character in folder for character in '<>"|?*'):
        return False
    drive, tail = ntpath.splitdrive(folder)
    if ":" in tail or (drive and not tail.startswith(("/", "\\"))):
        return False
    if not (ntpath.isabs(folder) or Path(folder).is_absolute()):
        return False
    if folder.startswith("\\\\") and (not drive or not tail):
        return False
    return True


def validate_settings(settings: Settings) -> Settings:
    """Validate and normalize a complete settings snapshot.

    Args:
        settings: Candidate preferences, normally collected from the GUI.

    Returns:
        A settings snapshot with canonical shortcut spelling.

    Raises:
        ConfigurationError: A field has the wrong type or violates its range.
    """
    if type(settings.schema_version) is not int or settings.schema_version != SCHEMA_VERSION:
        raise ConfigurationError("configuration.schema_invalid")
    integer_bounds: tuple[tuple[int, int, int, str], ...] = (
        (settings.idle_seconds, MIN_IDLE_SECONDS, MAX_IDLE_SECONDS, "idle"),
        (settings.distance_pixels, MIN_DISTANCE_PIXELS, MAX_DISTANCE_PIXELS, "distance"),
    )
    for value, lower, upper, name in integer_bounds:
        if type(value) is not int or not lower <= value <= upper:
            raise ConfigurationError(f"configuration.{name}_invalid")
    if (
        type(settings.duration_seconds) not in (int, float)
        or not math.isfinite(settings.duration_seconds)
        or not MIN_DURATION_SECONDS <= settings.duration_seconds <= MAX_DURATION_SECONDS
    ):
        raise ConfigurationError("configuration.duration_invalid")
    boolean_values: tuple[bool, ...] = (
        settings.mover_enabled,
        settings.prevent_sleep,
        settings.keep_displays_awake,
        settings.start_minimized,
        settings.start_with_windows,
    )
    if any(type(value) is not bool for value in boolean_values):
        raise ConfigurationError("configuration.boolean_invalid")
    if settings.pattern not in ("rectangle", "circle"):
        raise ConfigurationError("configuration.pattern_invalid")
    if settings.screenshot_mode not in ("all", "current", "each"):
        raise ConfigurationError("configuration.mode_invalid")
    if (
        not isinstance(settings.screenshot_folder, str)
        or not _valid_folder(settings.screenshot_folder)
    ):
        raise ConfigurationError("configuration.folder_invalid")
    if (
        not isinstance(settings.language, str)
        or not re.fullmatch(r"[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?", settings.language)
    ):
        raise ConfigurationError("configuration.language_invalid")
    try:
        hotkey: str = canonicalize_hotkey(settings.screenshot_hotkey)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error
    return replace(
        settings,
        duration_seconds=float(settings.duration_seconds),
        screenshot_hotkey=hotkey,
    )


class ConfigurationStore:
    """Versioned JSON store with bounded reads and atomic replacement.

    Attributes:
        path: Per-user settings filename.
        notices: Translation keys describing repairs made during the last load.
        read_only: True after loading an unsupported future schema.
    """

    def __init__(self, path: Path, default_screenshot_folder: Path) -> None:
        """Create a store without reading or creating files.

        Args:
            path: Full filename beneath the user's application-data folder.
            default_screenshot_folder: Actual known Pictures folder / SCR Tools.

        Returns:
            None.
        """
        self.path: Path = path
        self.notices: list[str] = []
        self.read_only: bool = False
        self._defaults: Settings = Settings(
            screenshot_folder=str(default_screenshot_folder)
        )

    def _backup_damaged_file(self) -> None:
        """Preserve damaged data under a unique adjacent backup filename.

        Returns:
            None. Backup errors are reported as notices without data deletion.
        """
        stamp: str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup: Path = self.path.with_name(f"{self.path.name}.broken.{stamp}")
        try:
            with self.path.open("rb") as source, backup.open("xb") as target:
                while chunk := source.read(64 * 1024):
                    target.write(chunk)
        except OSError:
            self.notices.append("configuration.backup_failed")

    def load(self) -> Settings:
        """Read settings, migrating legacy unversioned objects when possible.

        Returns:
            Validated preferences. Missing or invalid fields use their defaults.
            Future schemas expose supported fields and make this store read-only.
        """
        self.notices.clear()
        self.read_only = False
        if not self.path.exists():
            return self._defaults
        try:
            if self.path.stat().st_size > MAX_CONFIGURATION_BYTES:
                raise ValueError("oversized settings")
            raw: object = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings root is not an object")
        except (OSError, UnicodeError, ValueError, RecursionError):
            self.notices.append("configuration.damaged")
            self._backup_damaged_file()
            return self._defaults
        values: dict[str, object] = {
            key: value for key, value in raw.items() if isinstance(key, str)
        }
        version: object = values.get("schema_version", 0)
        if type(version) is not int or cast(int, version) < 0:
            self.notices.append("configuration.schema_invalid")
            return self._defaults
        if cast(int, version) > SCHEMA_VERSION:
            self.read_only = True
            self.notices.append("configuration.future_schema")
        elif version == 0:
            # Version 0 is the documented unversioned initial JSON format.
            self.notices.append("configuration.migrated")
        result: Settings = self._defaults
        for field in fields(Settings):
            if field.name == "schema_version" or field.name not in values:
                continue
            candidate: Settings = replace(result, **{field.name: values[field.name]})
            try:
                result = validate_settings(candidate)
            except ConfigurationError:
                self.notices.append("configuration.fields_reset")
        self.notices = list(dict.fromkeys(self.notices))
        return result

    def save(self, settings: Settings) -> None:
        """Atomically persist validated JSON while preserving a future schema.

        Args:
            settings: Complete candidate preferences.

        Returns:
            None after an fsync and atomic replacement in the same directory.

        Raises:
            FutureSchemaError: A newer schema was loaded by this store.
            ConfigurationError: Candidate values fail validation.
            OSError: Directory creation, writing, or replacement failed.
        """
        if self.read_only:
            raise FutureSchemaError("configuration.future_schema")
        checked: Settings = validate_settings(settings)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".settings-", suffix=".tmp", delete=False,
            ) as output:
                temporary_path = Path(output.name)
                json.dump(asdict(checked), output, indent=2, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
