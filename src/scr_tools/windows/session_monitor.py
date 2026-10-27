# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/session_monitor.py
# Module Type: Interactive-session state
# Purpose: Pause automation during lock, disconnect, secure desktop and sleep.
# Responsibilities: Combine session/power notifications with desktop access.
# Author: Rudolf Klusal
# License: MIT
"""Fail-closed session state is independent of the user's enabled preference."""

import ctypes
from collections.abc import Callable

from scr_tools.windows.native_api import DWORD, WindowsAPI

WTS_CONSOLE_CONNECT: int = 1
WTS_CONSOLE_DISCONNECT: int = 2
WTS_REMOTE_CONNECT: int = 3
WTS_REMOTE_DISCONNECT: int = 4
WTS_SESSION_LOGON: int = 5
WTS_SESSION_LOGOFF: int = 6
WTS_SESSION_LOCK: int = 7
WTS_SESSION_UNLOCK: int = 8
PBT_APMSUSPEND: int = 4
PBT_APMRESUMECRITICAL: int = 6
PBT_APMRESUMESUSPEND: int = 7
PBT_APMRESUMEAUTOMATIC: int = 18
WTS_CURRENT_SESSION: int = 0xFFFFFFFF
WTS_CONNECT_STATE: int = 8
WTS_ACTIVE: int = 0


def session_connected(api: WindowsAPI) -> bool:
    """Query the current session instead of assuming startup is connected.

    Args:
        api: Initialized Windows system API bindings.

    Returns:
        True only for WTSActive. A missing service, query failure, disconnected
        RDP session or incomplete state fails closed. Windows owns the buffer
        until WTSFreeMemory releases it in the finally block.
    """
    buffer = ctypes.c_void_p()
    size = DWORD()
    succeeded = api.wtsapi32.WTSQuerySessionInformationW(
        None, WTS_CURRENT_SESSION, WTS_CONNECT_STATE, ctypes.byref(buffer),
        ctypes.byref(size),
    )
    try:
        if not succeeded or not buffer or size.value < ctypes.sizeof(DWORD):
            return False
        state = ctypes.cast(buffer, ctypes.POINTER(DWORD)).contents.value
        return state == WTS_ACTIVE
    finally:
        if buffer:
            api.wtsapi32.WTSFreeMemory(buffer)


class SessionMonitor:
    """Track notifications plus periodic secure-desktop availability."""

    def __init__(self, accessible: Callable[[], bool],
                 connected: Callable[[], bool] | None = None) -> None:
        """Create conservative state for the current native host session.

        Args:
            accessible: Returns True only for the ordinary Default desktop.
            connected: Optional native WTSConnectState query. The native host
                supplies it to cover sessions disconnected before app startup.
        """
        self._accessible: Callable[[], bool] = accessible
        self._connected: Callable[[], bool] | None = connected
        self.locked: bool = False
        self.disconnected: bool = False
        self.suspended: bool = False

    def session_changed(self, reason: int) -> None:
        """Apply a WTS notification for this interactive session.

        Args:
            reason: Documented WM_WTSSESSION_CHANGE event identifier.

        Returns:
            None. Unknown reasons leave state unchanged.
        """
        if reason in (WTS_SESSION_LOCK, WTS_SESSION_LOGOFF):
            self.locked = True
        elif reason in (WTS_SESSION_UNLOCK, WTS_SESSION_LOGON):
            self.locked = False
        elif reason in (WTS_CONSOLE_DISCONNECT, WTS_REMOTE_DISCONNECT):
            self.disconnected = True
        elif reason in (WTS_CONSOLE_CONNECT, WTS_REMOTE_CONNECT):
            self.disconnected = False

    def power_changed(self, reason: int) -> None:
        """Apply suspend/resume notifications without defeating manual sleep.

        Args:
            reason: Documented WM_POWERBROADCAST event identifier.

        Returns:
            None. Unknown reasons leave state unchanged.
        """
        if reason == PBT_APMSUSPEND:
            self.suspended = True
        elif reason in (PBT_APMRESUMECRITICAL, PBT_APMRESUMESUSPEND,
                        PBT_APMRESUMEAUTOMATIC):
            self.suspended = False

    def interactive(self) -> bool:
        """Return True only when session policy and current desktop permit it."""
        return (not self.locked and not self.disconnected and
                not self.suspended and
                (self._connected is None or self._connected()) and
                self._accessible())
