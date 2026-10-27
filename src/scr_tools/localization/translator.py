# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/localization/translator.py
# Module Type: Localization
# Purpose: Resolve UI messages from resource catalogs with English fallbacks.
# Responsibilities: Catalog loading, locale fallback and safe value formatting.
# Author: Rudolf Klusal
# License: MIT

"""Flat JSON translation catalogs with independently maintained GUI resources."""

import json
import logging
import re
from pathlib import Path


type FormatValue = str | int | float
LOGGER: logging.Logger = logging.getLogger(__name__)
LANGUAGE_PATTERN: str = r"[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?"


def _read_catalog(path: Path) -> dict[str, str]:
    """Read only string-to-string entries from an optional JSON catalog.

    Args:
        path: Resource filename; absent optional language files are normal.

    Returns:
        Valid string entries, or an empty dictionary for an unreadable resource.
    """
    try:
        parsed: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, ValueError, RecursionError):
        LOGGER.error("A localization catalog could not be loaded")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        key: value for key, value in parsed.items()
        if isinstance(key, str) and isinstance(value, str)
    }


class Translator:
    """Merge domain and GUI catalogs with a complete English baseline.

    Attributes:
        language: Requested safe locale identifier. Unsupported locales simply
            render English while keeping the configured preference intact.
    """

    def __init__(self, language: str = "en", resource_directory: Path | None = None) -> None:
        """Load English catalogs and optional locale overrides.

        Args:
            language: Catalog identifier such as en or sv.
            resource_directory: Optional test/resource root; packaged execution
                uses the directory containing this module.

        Returns:
            None. Invalid locale identifiers safely select English.
        """
        self.language: str = (
            language if re.fullmatch(LANGUAGE_PATTERN, language) else "en"
        )
        directory: Path = resource_directory or Path(__file__).resolve().parent
        self._directory: Path = directory
        self._english: dict[str, str] = _read_catalog(directory / "en.json")
        self._english.update(_read_catalog(directory / "en.gui.json"))
        self._localized: dict[str, str] = dict(self._english)
        if self.language != "en":
            self._localized.update(_read_catalog(directory / f"{self.language}.json"))
            self._localized.update(_read_catalog(directory / f"{self.language}.gui.json"))

    def available_languages(self) -> dict[str, str]:
        """Discover locale resources without requiring GUI source changes.

        Returns:
            Locale codes mapped to their optional native ``language.display_name``
            resource value, falling back to the code. English is always included.
            GUI companion catalogs are excluded from locale discovery.
        """
        languages: dict[str, str] = {
            "en": self._english.get("language.display_name", "English")
        }
        try:
            paths: list[Path] = sorted(self._directory.glob("*.json"))
        except OSError:
            return languages
        for path in paths:
            code: str = path.stem
            if code == "en" or re.fullmatch(LANGUAGE_PATTERN, code) is None:
                continue
            catalog: dict[str, str] = _read_catalog(path)
            languages[code] = catalog.get("language.display_name", code)
        return languages

    def text(self, key: str, **values: FormatValue) -> str:
        """Resolve and format a message without allowing translation failures.

        Args:
            key: Stable English-catalog identifier.
            **values: Primitive replacement values named by the message template.

        Returns:
            Formatted localized text, or English on a missing/broken translation.
            An unknown key is returned verbatim to expose an incomplete catalog.
        """
        english: str = self._english.get(key, key)
        localized: str = self._localized.get(key, english)
        for template in (localized, english):
            try:
                return template.format(**values)
            except (KeyError, ValueError, IndexError, AttributeError):
                continue
        return english

    def has_key(self, key: str) -> bool:
        """Check that an English fallback exists for a stable message identifier.

        Args:
            key: Message identifier used by application source.

        Returns:
            True when the English catalog contains this key.
        """
        return key in self._english
