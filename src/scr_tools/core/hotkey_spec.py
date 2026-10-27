# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/core/hotkey_spec.py
# Module Type: Domain value parsing
# Purpose: Parse configurable Windows global shortcuts consistently.
# Responsibilities: Validate keys and produce RegisterHotKey-compatible flags.
# Author: Rudolf Klusal
# License: MIT

"""Validated global shortcut definitions without loading Windows libraries."""

from dataclasses import dataclass


MODIFIER_FLAGS: dict[str, int] = {
    "Ctrl": 0x0002,
    "Alt": 0x0001,
    "Shift": 0x0004,
    "Win": 0x0008,
}
SPECIAL_KEYS: dict[str, int] = {
    "PrintScreen": 0x2C,
    "Pause": 0x13,
    "Insert": 0x2D,
    "Delete": 0x2E,
    "Home": 0x24,
    "End": 0x23,
    "PageUp": 0x21,
    "PageDown": 0x22,
    "Space": 0x20,
}


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    """A canonical shortcut and its native RegisterHotKey parameters.

    Attributes:
        modifiers: Win32 modifier bits, excluding MOD_NOREPEAT.
        key_code: A supported virtual-key code.
        label: Canonical English shortcut spelling for configuration.
    """

    modifiers: int
    key_code: int
    label: str


def parse_hotkey(text: str) -> HotkeySpec:
    """Validate a shortcut containing modifiers and exactly one key.

    Args:
        text: A case-insensitive shortcut such as ``Ctrl+Shift+F11``.

    Returns:
        The canonical shortcut and documented Win32 bit values.

    Raises:
        ValueError: The syntax is invalid, has no modifier, or uses F12,
            which Windows reserves for debuggers.
    """
    if not isinstance(text, str):
        raise ValueError("hotkey.invalid")
    parts: list[str] = [part.strip().casefold() for part in text.split("+")]
    if len(parts) < 2 or any(not part for part in parts):
        raise ValueError("hotkey.invalid")
    modifier_names: dict[str, str] = {
        name.casefold(): name for name in MODIFIER_FLAGS
    }
    modifier_names["control"] = "Ctrl"
    modifiers: set[str] = set()
    key_parts: list[str] = []
    for part in parts:
        if part in modifier_names:
            name: str = modifier_names[part]
            if name in modifiers:
                raise ValueError("hotkey.invalid")
            modifiers.add(name)
        else:
            key_parts.append(part)
    if not modifiers or len(key_parts) != 1:
        raise ValueError("hotkey.invalid")
    key: str = key_parts[0]
    label: str
    key_code: int
    if len(key) == 1 and key.isascii() and key.isalnum():
        label = key.upper()
        key_code = ord(label)
    elif key.startswith("f") and key[1:].isdigit():
        number: int = int(key[1:])
        if not 1 <= number <= 24 or number == 12:
            raise ValueError("hotkey.reserved" if number == 12 else "hotkey.invalid")
        label = f"F{number}"
        key_code = 0x70 + number - 1
    else:
        matching: list[str] = [
            name for name in SPECIAL_KEYS if name.casefold() == key
        ]
        if not matching:
            raise ValueError("hotkey.invalid")
        label = matching[0]
        key_code = SPECIAL_KEYS[label]
    ordered: list[str] = [name for name in MODIFIER_FLAGS if name in modifiers]
    flags: int = sum(MODIFIER_FLAGS[name] for name in ordered)
    return HotkeySpec(flags, key_code, "+".join([*ordered, label]))


def canonicalize_hotkey(text: str) -> str:
    """Return the normalized spelling of a valid shortcut.

    Args:
        text: A configurable global shortcut string.

    Returns:
        Canonical modifier order and key capitalization.

    Raises:
        ValueError: See :func:`parse_hotkey` for invalid shortcut cases.
    """
    return parse_hotkey(text).label
