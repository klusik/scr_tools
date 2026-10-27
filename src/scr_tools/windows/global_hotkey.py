# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/global_hotkey.py
# Module Type: Native global shortcut registration
# Purpose: Register a nonrepeating screenshot shortcut transactionally.
# Responsibilities: Preserve prior shortcuts on rebind conflicts and cleanup.
# Author: Rudolf Klusal
# License: MIT
"""Register a replacement before removing the currently working hotkey."""

from collections.abc import Callable

from scr_tools.core.hotkey_spec import parse_hotkey

MOD_NOREPEAT: int = 0x4000
HOTKEY_IDS: tuple[int, int] = (11, 12)


class GlobalHotkey:
    """Thread-owned, conflict-safe RegisterHotKey adapter."""

    def __init__(self, register: Callable[[int, int, int], bool],
                 unregister: Callable[[int], bool]) -> None:
        """Create a registration adapter for one native host window.

        Args:
            register: Callable accepting identifier, modifier bits and VK.
            unregister: Callable accepting an identifier and returning success.
        """
        self._register: Callable[[int, int, int], bool] = register
        self._unregister: Callable[[int], bool] = unregister
        self.identifier: int | None = None
        self.label: str = ""

    def bind(self, text: str) -> str:
        """Bind a canonical shortcut while preserving the previous one.

        Args:
            text: Valid user shortcut such as Ctrl+Shift+F11.

        Returns:
            The actual canonical registered shortcut.

        Raises:
            ValueError: The shortcut syntax is invalid or reserved.
            OSError: Windows rejects the new registration or cannot remove the
                previous one. The old registration is retained on conflicts.
        """
        specification = parse_hotkey(text)
        if self.identifier is not None and specification.label == self.label:
            return self.label
        candidate = (HOTKEY_IDS[1] if self.identifier == HOTKEY_IDS[0]
                     else HOTKEY_IDS[0])
        if not self._register(candidate, specification.modifiers | MOD_NOREPEAT,
                              specification.key_code):
            raise OSError("Global shortcut is already registered or unavailable")
        if self.identifier is not None and not self._unregister(self.identifier):
            self._unregister(candidate)
            raise OSError("Previous global shortcut could not be unregistered")
        self.identifier = candidate
        self.label = specification.label
        return self.label

    def close(self) -> None:
        """Unregister the active shortcut, reporting a native failure.

        Raises:
            OSError: An active registration could not be removed.
        """
        if self.identifier is not None:
            if not self._unregister(self.identifier):
                raise OSError("Global shortcut could not be unregistered")
            self.identifier = None
            self.label = ""
