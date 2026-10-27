# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/single_instance.py
# Module Type: Windows process lifecycle
# Purpose: Enforce one application per interactive Windows session.
# Responsibilities: Hold a named mutex and request existing-window activation.
# Author: Rudolf Klusal
# License: MIT
"""A session-scoped kernel mutex outlives no process and needs no lock file."""

import ctypes
import time

from scr_tools.windows.native_api import (
    DWORD, MUTEX_NAME, WINDOW_CLASS, WINDOW_TITLE, WM_ACTIVATE_INSTANCE,
    WindowsAPI, windows_error,
)

ERROR_ALREADY_EXISTS: int = 183
ACTIVATION_TIMEOUT_SECONDS: float = 5.0
ACTIVATION_RETRY_SECONDS: float = 0.05


class SingleInstance:
    """Hold a session-local mutex and find the original native host window."""

    def __init__(self) -> None:
        """Initialize the native bindings without acquiring a mutex."""
        self.api: WindowsAPI = WindowsAPI()
        self._handle: int | None = None
        self._owner: bool = False

    def acquire(self) -> bool:
        """Acquire the unique process slot without waiting on another process.

        Returns:
            True for the first process; False when another process already
            holds the mutex. Repeat calls return the initial result.

        Raises:
            OSError: Windows cannot create/open the named mutex.
        """
        if self._handle is not None:
            return self._owner
        ctypes.set_last_error(0)
        handle = self.api.kernel32.CreateMutexW(None, False, MUTEX_NAME)
        error = ctypes.get_last_error()
        if not handle:
            raise windows_error("CreateMutexW", error)
        self._handle = int(handle)
        self._owner = error != ERROR_ALREADY_EXISTS
        return self._owner

    def activate_existing(self) -> bool:
        """Request that the original process restore and focus its Tk window.

        Returns:
            True when the activation message was posted. False if no host
            window becomes available within five seconds. The retry handles
            a second launch during first-process initialization. Call this
            before constructing the second process's GUI, never on its Tk
            event loop.
        """
        deadline = time.monotonic() + ACTIVATION_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            window = self.api.user32.FindWindowW(WINDOW_CLASS, WINDOW_TITLE)
            if window:
                process_id = DWORD()
                self.api.user32.GetWindowThreadProcessId(
                    window, ctypes.byref(process_id)
                )
                if process_id.value:
                    self.api.user32.AllowSetForegroundWindow(process_id.value)
                return bool(self.api.user32.PostMessageW(
                    window, WM_ACTIVATE_INSTANCE, 0, 0
                ))
            time.sleep(ACTIVATION_RETRY_SECONDS)
        return False

    def close(self) -> None:
        """Release the kernel handle; no persistent mutex object remains."""
        if self._handle is not None:
            self.api.kernel32.CloseHandle(self._handle)
            self._handle = None
            self._owner = False
