# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/tray_icon.py
# Module Type: Native Windows notification-area UI
# Purpose: Keep an always-registered tray icon and the sole normal Exit action.
# Responsibilities: Shell registration, translated menu, Explorer recovery.
# Author: Rudolf Klusal
# License: MIT
"""Native tray resources belong to the same thread as their host window."""

import ctypes
from collections.abc import Callable
from pathlib import Path

from scr_tools.windows.native_api import (
    NOTIFYICONDATAW, POINT, WM_TRAY, WindowsAPI, windows_error,
)

NIM_ADD: int = 0
NIM_DELETE: int = 2
NIM_SETVERSION: int = 4
NIF_MESSAGE: int = 0x01
NIF_ICON: int = 0x02
NIF_TIP: int = 0x04
NIF_SHOWTIP: int = 0x80
NOTIFYICON_VERSION_4: int = 4
TRAY_ICON_ID: int = 1
MENU_OPEN: int = 101
MENU_CAPTURE: int = 103
MENU_EXIT: int = 104


class TrayIcon:
    """Own a proper .ico resource and a translated native context menu."""

    def __init__(self, api: WindowsAPI, window: int, icon_path: Path,
                 translate: Callable[[str], str]) -> None:
        """Load the icon without registering it prematurely.

        Args:
            api: Native API bound on the message-pump thread.
            window: Hidden top-level window receiving shell callbacks.
            icon_path: Existing multi-resolution .ico file.
            translate: Thread-safe catalog lookup with English fallback.

        Raises:
            OSError: Windows cannot load the icon resource.
        """
        self._api: WindowsAPI = api
        self._window: int = window
        self._translate: Callable[[str], str] = translate
        self.registered: bool = False
        icon = api.user32.LoadImageW(
            None, str(icon_path), 1, api.user32.GetSystemMetrics(49),
            api.user32.GetSystemMetrics(50), 0x0010
        )
        if not icon:
            raise windows_error("LoadImageW(application icon)")
        self._icon: int | None = int(icon)

    def register(self) -> bool:
        """Register/re-register the icon after startup or Explorer restart.

        Returns:
            True when the icon is registered with version-4 shell callbacks.
            False when Explorer is unavailable; the host retries later.
        """
        information = self._data()
        if not self._api.shell32.Shell_NotifyIconW(
            NIM_ADD, ctypes.byref(information)
        ):
            self.registered = False
            return False
        information.uVersion = NOTIFYICON_VERSION_4
        if not self._api.shell32.Shell_NotifyIconW(
            NIM_SETVERSION, ctypes.byref(information)
        ):
            self._api.shell32.Shell_NotifyIconW(
                NIM_DELETE, ctypes.byref(information)
            )
            self.registered = False
            return False
        self.registered = True
        return True

    def show_menu(self) -> str | None:
        """Display the compact translated menu and return the chosen action.

        Returns:
            str | None: open, capture, exit, or None when dismissed.

        Raises:
            OSError: Windows cannot create or populate the popup menu.
        """
        menu = self._api.user32.CreatePopupMenu()
        if not menu:
            raise windows_error("CreatePopupMenu")
        try:
            entries = (
                (MENU_OPEN, "tray.open"),
                (MENU_CAPTURE, "tray.capture"),
                (0, ""),
                (MENU_EXIT, "tray.exit"),
            )
            for identifier, key in entries:
                flags = 0x0800 if identifier == 0 else 0
                label = None if identifier == 0 else self._translate(key)
                if not self._api.user32.AppendMenuW(
                    menu, flags, identifier, label
                ):
                    raise windows_error("AppendMenuW")
            point = POINT()
            if not self._api.user32.GetCursorPos(ctypes.byref(point)):
                raise windows_error("GetCursorPos(tray menu)")
            self._api.user32.SetForegroundWindow(self._window)
            selected = self._api.user32.TrackPopupMenu(
                menu, 0x0100 | 0x0080 | 0x0002, point.x, point.y, 0,
                self._window, None
            )
            # The documented WM_NULL post allows dismissal on a later outside
            # click after SetForegroundWindow has made the menu owner active.
            self._api.user32.PostMessageW(self._window, 0, 0, 0)
            actions: dict[int, str] = {
                MENU_OPEN: "open",
                MENU_CAPTURE: "capture", MENU_EXIT: "exit",
            }
            return actions.get(int(selected))
        finally:
            self._api.user32.DestroyMenu(menu)

    def close(self) -> None:
        """Remove the registered icon and release the loaded HICON."""
        if self.registered:
            information = self._data()
            self._api.shell32.Shell_NotifyIconW(
                NIM_DELETE, ctypes.byref(information)
            )
            self.registered = False
        if self._icon is not None:
            self._api.user32.DestroyIcon(self._icon)
            self._icon = None

    def _data(self) -> NOTIFYICONDATAW:
        """Return a complete notification record with no balloon content."""
        information = NOTIFYICONDATAW()
        information.cbSize = ctypes.sizeof(information)
        information.hWnd = self._window
        information.uID = TRAY_ICON_ID
        information.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
        information.uCallbackMessage = WM_TRAY
        information.hIcon = self._icon
        information.szTip = self._translate("app.title")[:127]
        return information
