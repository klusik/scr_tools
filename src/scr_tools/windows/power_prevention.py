# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/power_prevention.py
# Module Type: Thread-owned Windows power request
# Purpose: Prevent automatic system sleep while background services are ready.
# Responsibilities: Acquire, update and release execution-state requirements.
# Author: Rudolf Klusal
# License: MIT
"""SetThreadExecutionState requests must be managed on one stable thread."""

from collections.abc import Callable
from threading import get_ident

ES_CONTINUOUS: int = 0x80000000
ES_SYSTEM_REQUIRED: int = 0x00000001
ES_DISPLAY_REQUIRED: int = 0x00000002


class PowerPrevention:
    """Own the native host thread's continuous power request."""

    def __init__(self, set_state: Callable[[int], int]) -> None:
        """Capture the creating thread and its execution-state function.

        Args:
            set_state: SetThreadExecutionState-compatible callable. A zero
                result means failure; a nonzero result means success.
        """
        self._set_state: Callable[[int], int] = set_state
        self._thread_id: int = get_ident()
        self.flags: int = ES_CONTINUOUS

    def configure(self, mover_enabled: bool, prevent_sleep: bool,
                  keep_displays_awake: bool, interactive: bool) -> bool:
        """Update power requirements on the owning native thread.

        Args:
            mover_enabled: Whether background services and hooks are ready.
            prevent_sleep: Whether automatic system sleep is prevented.
            keep_displays_awake: Whether display sleep should also be blocked.
            interactive: Whether the ordinary user desktop is available.

        Returns:
            True if a continuous system requirement is currently active.

        Raises:
            RuntimeError: Called from a different thread.
            OSError: Windows rejected the execution-state request.
        """
        self._check_thread()
        flags = ES_CONTINUOUS
        if mover_enabled and prevent_sleep and interactive:
            flags |= ES_SYSTEM_REQUIRED
            if keep_displays_awake:
                flags |= ES_DISPLAY_REQUIRED
        if flags != self.flags:
            if not self._set_state(flags):
                raise OSError("SetThreadExecutionState rejected the request")
            self.flags = flags
        return bool(self.flags & ES_SYSTEM_REQUIRED)

    def release(self) -> None:
        """Explicitly release this thread's request, including during exit.

        Raises:
            RuntimeError: Called from a different thread.
            OSError: Windows rejected the release request.
        """
        self._check_thread()
        if not self._set_state(ES_CONTINUOUS):
            raise OSError("SetThreadExecutionState release failed")
        self.flags = ES_CONTINUOUS

    def _check_thread(self) -> None:
        """Raise RuntimeError if execution-state ownership is violated."""
        if get_ident() != self._thread_id:
            raise RuntimeError("Power state must be changed by its owner thread")
