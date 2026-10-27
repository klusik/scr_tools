# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/input_monitor.py
# Module Type: Session-wide input occurrence detector
# Purpose: Observe input occurrences without recording keys or text.
# Responsibilities: Own low-level hooks and always forward their events.
# Author: Rudolf Klusal
# License: MIT
"""Hooks run on the native host's message-pump thread and never suppress input."""

import ctypes
from collections.abc import Callable

from scr_tools.windows.native_api import (
    HOOKPROC, KBDLLHOOKSTRUCT, MSLLHOOKSTRUCT, WindowsAPI, windows_error,
)

WH_KEYBOARD_LL: int = 13
WH_MOUSE_LL: int = 14
LLMHF_INJECTED: int = 0x01
LLKHF_INJECTED: int = 0x10


class InputMonitor:
    """Keep callbacks alive while monitoring mouse and keyboard occurrences."""

    def __init__(self, api: WindowsAPI,
                 on_input: Callable[[int, bool], None]) -> None:
        """Store a constant-time activity callback and native API.

        Args:
            api: Native bindings owned by the host thread.
            on_input: Receives only dwExtraInfo and the injected flag. It must
                only update bounded in-memory activity state and return.
        """
        self._api: WindowsAPI = api
        self._on_input: Callable[[int, bool], None] = on_input
        self._mouse_hook: int | None = None
        self._keyboard_hook: int | None = None
        self._mouse_callback = HOOKPROC(self._mouse_event)
        self._keyboard_callback = HOOKPROC(self._keyboard_event)
        self.callback_failed: bool = False

    @property
    def ready(self) -> bool:
        """Return True while both installed hooks have valid handles."""
        return (self._mouse_hook is not None and
                self._keyboard_hook is not None and not self.callback_failed)

    def install(self) -> None:
        """Install both hooks on the current message-pump thread.

        Raises:
            OSError: Windows rejects either hook; an already installed first
                hook is removed before the failure leaves this method.
        """
        if self.ready:
            return
        self.close()
        module = self._api.kernel32.GetModuleHandleW(None)
        mouse = self._api.user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_callback, module, 0
        )
        if not mouse:
            raise windows_error("SetWindowsHookExW(mouse)")
        self._mouse_hook = int(mouse)
        keyboard = self._api.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._keyboard_callback, module, 0
        )
        if not keyboard:
            error = windows_error("SetWindowsHookExW(keyboard)")
            self.close()
            raise error
        self._keyboard_hook = int(keyboard)
        self.callback_failed = False

    def close(self) -> None:
        """Remove both hooks while preserving callback objects until removal."""
        if self._mouse_hook is not None:
            self._api.user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        if self._keyboard_hook is not None:
            self._api.user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None

    def _mouse_event(self, code: int, message: int, pointer: int) -> int:
        """Record one occurrence and immediately continue the hook chain.

        Args:
            code: Hook action code; negative values are passed through.
            message: Windows input message identifier; never retained.
            pointer: Borrowed MSLLHOOKSTRUCT pointer valid in this call.

        Returns:
            The next hook's result without suppressing any event.
        """
        if code >= 0:
            try:
                data = ctypes.cast(pointer,
                                   ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                self._on_input(int(data.dwExtraInfo),
                               bool(data.flags & LLMHF_INJECTED))
            except Exception:
                # Exceptions must never unwind into Windows or disrupt input.
                # The host polls this flag and disables unsafe automation.
                self.callback_failed = True
        return int(self._api.user32.CallNextHookEx(
            None, code, message, pointer
        ))

    def _keyboard_event(self, code: int, message: int, pointer: int) -> int:
        """Record key activity without reading or retaining key identities.

        Args:
            code: Hook action code; negative values are passed through.
            message: Windows message identifier; never retained.
            pointer: Borrowed KBDLLHOOKSTRUCT pointer valid in this call.

        Returns:
            The next hook's result without suppressing any event.
        """
        if code >= 0:
            try:
                data = ctypes.cast(pointer,
                                   ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                self._on_input(int(data.dwExtraInfo),
                               bool(data.flags & LLKHF_INJECTED))
            except Exception:
                self.callback_failed = True
        return int(self._api.user32.CallNextHookEx(
            None, code, message, pointer
        ))
