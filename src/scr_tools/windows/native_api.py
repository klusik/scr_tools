# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/native_api.py
# Module Type: Windows foreign-function interface
# Purpose: Declare pointer-safe Windows API types and function signatures.
# Responsibilities: DLL loading, ABI layouts, constants, and checked errors.
# Author: Rudolf Klusal
# License: MIT
"""Explicit Windows x64 ABI declarations without loading DLLs at import time."""

import ctypes
import sys

BOOL = ctypes.c_int32
DWORD = ctypes.c_uint32
UINT = ctypes.c_uint32
LONG = ctypes.c_int32
WORD = ctypes.c_uint16
ULONG_PTR = ctypes.c_size_t
LONG_PTR = ctypes.c_ssize_t
HANDLE = ctypes.c_void_p
LPCWSTR = ctypes.c_wchar_p
LPVOID = ctypes.c_void_p
CALLBACK = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WNDPROC = CALLBACK(LONG_PTR, HANDLE, UINT, ULONG_PTR, LONG_PTR)
HOOKPROC = CALLBACK(LONG_PTR, ctypes.c_int, ULONG_PTR, LONG_PTR)


class POINT(ctypes.Structure):
    """Two signed physical-pixel coordinates in the Windows LONG ABI."""

    _fields_ = [("x", LONG), ("y", LONG)]


class RECT(ctypes.Structure):
    """Physical-pixel rectangle with exclusive right and bottom edges."""

    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG),
                ("bottom", LONG)]


class MSG(ctypes.Structure):
    """Message-loop structure, including the reserved private DWORD."""

    _fields_ = [("hwnd", HANDLE), ("message", UINT), ("wParam", ULONG_PTR),
                ("lParam", LONG_PTR), ("time", DWORD), ("pt", POINT),
                ("lPrivate", DWORD)]


class WNDCLASSEXW(ctypes.Structure):
    """Unicode top-level window class with a persistent callback pointer."""

    _fields_ = [("cbSize", UINT), ("style", UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", HANDLE), ("hIcon", HANDLE), ("hCursor", HANDLE),
                ("hbrBackground", HANDLE), ("lpszMenuName", LPCWSTR),
                ("lpszClassName", LPCWSTR), ("hIconSm", HANDLE)]


class MONITORINFO(ctypes.Structure):
    """Monitor geometry in the physical virtual-desktop coordinate space."""

    _fields_ = [("cbSize", DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                ("dwFlags", DWORD)]


class MOUSEINPUT(ctypes.Structure):
    """Mouse input, preserving pointer-sized dwExtraInfo on Windows x64."""

    _fields_ = [("dx", LONG), ("dy", LONG), ("mouseData", DWORD),
                ("dwFlags", DWORD), ("time", DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    """Keyboard member needed to represent the complete INPUT union."""

    _fields_ = [("wVk", WORD), ("wScan", WORD), ("dwFlags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    """Hardware member needed to represent the complete INPUT union."""

    _fields_ = [("uMsg", DWORD), ("wParamL", WORD), ("wParamH", WORD)]


class INPUTUNION(ctypes.Union):
    """Native input union; omitting members can change INPUT alignment."""

    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT),
                ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    """Documented SendInput record, 40 bytes on Windows x64."""

    _anonymous_ = ("value",)
    _fields_ = [("type", DWORD), ("value", INPUTUNION)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    """Only flags and extra information are inspected by the mouse hook."""

    _fields_ = [("pt", POINT), ("mouseData", DWORD), ("flags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Keyboard hook ABI; key and scan-code fields are never retained."""

    _fields_ = [("vkCode", DWORD), ("scanCode", DWORD), ("flags", DWORD),
                ("time", DWORD), ("dwExtraInfo", ULONG_PTR)]


class GUID(ctypes.Structure):
    """Windows GUID layout, used by shell known-folder APIs."""

    _fields_ = [("Data1", DWORD), ("Data2", WORD), ("Data3", WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    """Full modern Unicode notification-area icon data."""

    _fields_ = [("cbSize", DWORD), ("hWnd", HANDLE), ("uID", UINT),
                ("uFlags", UINT), ("uCallbackMessage", UINT),
                ("hIcon", HANDLE), ("szTip", ctypes.c_wchar * 128),
                ("dwState", DWORD), ("dwStateMask", DWORD),
                ("szInfo", ctypes.c_wchar * 256), ("uVersion", UINT),
                ("szInfoTitle", ctypes.c_wchar * 64),
                ("dwInfoFlags", DWORD), ("guidItem", GUID),
                ("hBalloonIcon", HANDLE)]


MONITORENUMPROC = CALLBACK(BOOL, HANDLE, HANDLE, ctypes.POINTER(RECT), LONG_PTR)

# A hidden top-level window, rather than HWND_MESSAGE, receives shell restart,
# session and power broadcasts. Local\\ scopes the mutex to the Windows session.
WINDOW_CLASS: str = "SCRTools.NativeHost.0.1"
WINDOW_TITLE: str = "SCR Tools Native Host"
MUTEX_NAME: str = "Local\\SCRTools.RudolfKlusal.Singleton"
WM_APP: int = 0x8000
WM_COMMAND_QUEUE: int = WM_APP + 1
WM_TRAY: int = WM_APP + 2
WM_ACTIVATE_INSTANCE: int = WM_APP + 3


def windows_error(operation: str, code: int | None = None) -> OSError:
    """Build an operational error without attaching user-input contents.

    Args:
        operation: API name or short operational context.
        code: Explicit Win32 code, or None to read the thread's last error.

    Returns:
        OSError containing the numeric Windows error code and operation.
    """
    number = code if code is not None else ctypes.get_last_error()
    return OSError(number, f"{operation} failed (Windows error {number})")


class WindowsAPI:
    """Load Windows DLLs only when native functionality is instantiated."""

    def __init__(self) -> None:
        """Load and bind the x64 API.

        Raises:
            OSError: The process is not a 64-bit Windows process.
        """
        if sys.platform != "win32" or ctypes.sizeof(HANDLE) != 8:
            raise OSError("SCR Tools requires 64-bit Windows 11")
        self.user32: ctypes.CDLL = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32: ctypes.CDLL = ctypes.WinDLL("kernel32", use_last_error=True)
        self.shell32: ctypes.CDLL = ctypes.WinDLL("shell32", use_last_error=True)
        self.ole32: ctypes.CDLL = ctypes.WinDLL("ole32", use_last_error=True)
        self.wtsapi32: ctypes.CDLL = ctypes.WinDLL("wtsapi32", use_last_error=True)
        self._bind_user32()
        self._bind_system()

    @staticmethod
    def _bind(library: ctypes.CDLL, name: str, result: type | None,
              arguments: tuple[type, ...]) -> None:
        """Assign a C function's complete ABI before its first call.

        Args:
            library: Loaded system DLL.
            name: Exported Windows API name.
            result: ctypes result class, or None for void.
            arguments: Ordered ctypes argument classes.

        Returns:
            None. The DLL function object is configured in place.
        """
        function = getattr(library, name)
        function.restype = result
        function.argtypes = list(arguments)

    def _bind_user32(self) -> None:
        """Configure user-interface, input and message-loop exports."""
        definitions: list[tuple[str, type | None, tuple[type, ...]]] = [
            ("GetCursorPos", BOOL, (ctypes.POINTER(POINT),)),
            ("GetAsyncKeyState", ctypes.c_int16, (ctypes.c_int,)),
            ("GetSystemMetrics", ctypes.c_int, (ctypes.c_int,)),
            ("MonitorFromPoint", HANDLE, (POINT, DWORD)),
            ("GetMonitorInfoW", BOOL, (HANDLE, ctypes.POINTER(MONITORINFO))),
            ("EnumDisplayMonitors", BOOL,
             (HANDLE, LPVOID, MONITORENUMPROC, LONG_PTR)),
            ("SendInput", UINT, (UINT, ctypes.POINTER(INPUT), ctypes.c_int)),
            ("OpenInputDesktop", HANDLE, (DWORD, BOOL, DWORD)),
            ("CloseDesktop", BOOL, (HANDLE,)),
            ("GetUserObjectInformationW", BOOL,
             (HANDLE, ctypes.c_int, LPVOID, DWORD, ctypes.POINTER(DWORD))),
            ("SetProcessDpiAwarenessContext", BOOL, (HANDLE,)),
            ("RegisterClassExW", WORD, (ctypes.POINTER(WNDCLASSEXW),)),
            ("UnregisterClassW", BOOL, (LPCWSTR, HANDLE)),
            ("CreateWindowExW", HANDLE,
             (DWORD, LPCWSTR, LPCWSTR, DWORD, ctypes.c_int, ctypes.c_int,
              ctypes.c_int, ctypes.c_int, HANDLE, HANDLE, HANDLE, LPVOID)),
            ("DestroyWindow", BOOL, (HANDLE,)),
            ("DefWindowProcW", LONG_PTR, (HANDLE, UINT, ULONG_PTR, LONG_PTR)),
            ("GetMessageW", ctypes.c_int,
             (ctypes.POINTER(MSG), HANDLE, UINT, UINT)),
            ("TranslateMessage", BOOL, (ctypes.POINTER(MSG),)),
            ("DispatchMessageW", LONG_PTR, (ctypes.POINTER(MSG),)),
            ("PostQuitMessage", None, (ctypes.c_int,)),
            ("PostMessageW", BOOL, (HANDLE, UINT, ULONG_PTR, LONG_PTR)),
            ("PostThreadMessageW", BOOL, (DWORD, UINT, ULONG_PTR, LONG_PTR)),
            ("RegisterWindowMessageW", UINT, (LPCWSTR,)),
            ("SetTimer", ULONG_PTR, (HANDLE, ULONG_PTR, UINT, LPVOID)),
            ("KillTimer", BOOL, (HANDLE, ULONG_PTR)),
            ("SetWindowsHookExW", HANDLE,
             (ctypes.c_int, HOOKPROC, HANDLE, DWORD)),
            ("UnhookWindowsHookEx", BOOL, (HANDLE,)),
            ("CallNextHookEx", LONG_PTR,
             (HANDLE, ctypes.c_int, ULONG_PTR, LONG_PTR)),
            ("RegisterHotKey", BOOL, (HANDLE, ctypes.c_int, UINT, UINT)),
            ("UnregisterHotKey", BOOL, (HANDLE, ctypes.c_int)),
            ("LoadImageW", HANDLE,
             (HANDLE, LPCWSTR, UINT, ctypes.c_int, ctypes.c_int, UINT)),
            ("DestroyIcon", BOOL, (HANDLE,)),
            ("CreatePopupMenu", HANDLE, ()),
            ("AppendMenuW", BOOL, (HANDLE, UINT, ULONG_PTR, LPCWSTR)),
            ("DestroyMenu", BOOL, (HANDLE,)),
            ("TrackPopupMenu", UINT,
             (HANDLE, UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
              HANDLE, LPVOID)),
            ("SetForegroundWindow", BOOL, (HANDLE,)),
            ("FindWindowW", HANDLE, (LPCWSTR, LPCWSTR)),
            ("GetWindowThreadProcessId", DWORD,
             (HANDLE, ctypes.POINTER(DWORD))),
            ("AllowSetForegroundWindow", BOOL, (DWORD,)),
        ]
        for name, result, arguments in definitions:
            self._bind(self.user32, name, result, arguments)

    def _bind_system(self) -> None:
        """Configure kernel, shell, memory and Windows session exports."""
        self._bind(self.kernel32, "GetModuleHandleW", HANDLE, (LPCWSTR,))
        self._bind(self.kernel32, "GetCurrentThreadId", DWORD, ())
        self._bind(self.kernel32, "SetThreadExecutionState", DWORD, (DWORD,))
        self._bind(self.kernel32, "CreateMutexW", HANDLE,
                   (LPVOID, BOOL, LPCWSTR))
        self._bind(self.kernel32, "CloseHandle", BOOL, (HANDLE,))
        self._bind(self.shell32, "Shell_NotifyIconW", BOOL,
                   (DWORD, ctypes.POINTER(NOTIFYICONDATAW)))
        self._bind(self.shell32, "SHGetKnownFolderPath", LONG,
                   (ctypes.POINTER(GUID), DWORD, HANDLE,
                    ctypes.POINTER(ctypes.c_wchar_p)))
        self._bind(self.ole32, "CoTaskMemFree", None, (LPVOID,))
        self._bind(self.wtsapi32, "WTSRegisterSessionNotification", BOOL,
                   (HANDLE, DWORD))
        self._bind(self.wtsapi32, "WTSUnRegisterSessionNotification", BOOL,
                   (HANDLE,))
        self._bind(self.wtsapi32, "WTSQuerySessionInformationW", BOOL,
                   (HANDLE, DWORD, ctypes.c_int, ctypes.POINTER(LPVOID),
                    ctypes.POINTER(DWORD)))
        self._bind(self.wtsapi32, "WTSFreeMemory", None, (LPVOID,))
