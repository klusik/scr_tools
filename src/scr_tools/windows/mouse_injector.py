# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/mouse_injector.py
# Module Type: Windows input adapter
# Purpose: Send identifiable absolute mouse movement into Windows input.
# Responsibilities: Physical geometry, desktop checks, and SendInput events.
# Author: Rudolf Klusal
# License: MIT
"""Physical-pixel mouse injection; this module never synthesizes buttons."""

import ctypes

from scr_tools.windows.native_api import (
    DWORD, INPUT, MONITORENUMPROC, MONITORINFO, POINT, RECT, WindowsAPI,
    windows_error,
)

Point = tuple[int, int]
Bounds = tuple[int, int, int, int]
MOUSEEVENTF_MOVE: int = 0x0001
MOUSEEVENTF_MOVE_NOCOALESCE: int = 0x2000
MOUSEEVENTF_VIRTUALDESK: int = 0x4000
MOUSEEVENTF_ABSOLUTE: int = 0x8000
ABSOLUTE_RANGE: int = 65536
# Windows 11 can return only the low DWORD of SendInput's dwExtraInfo to
# WH_MOUSE_LL, despite the pointer-sized ABI. Keep identifiers in that range
# and compare them exactly; masking incoming foreign markers would ignore
# unrelated injected events that happen to share the same low DWORD.
MAX_INPUT_MARKER: int = 0xFFFFFFFF
DESKTOP_READOBJECTS: int = 0x0001
UOI_NAME: int = 2
MOUSE_BUTTON_KEYS: tuple[int, ...] = (0x01, 0x02, 0x04, 0x05, 0x06)


def normalize_coordinate(position: int, origin: int, extent: int) -> int:
    """Map a physical pixel to the center of its absolute-input interval.

    The 65,536 absolute coordinates represent intervals rather than a floating
    point line. Choosing an interval center avoids one-pixel rounding errors
    that arise when simply multiplying by 65,535 / (extent - 1).

    Args:
        position: Requested physical coordinate along one axis.
        origin: Minimum virtual-desktop coordinate on that axis.
        extent: Virtual-desktop size, from 1 through 65,536 physical pixels.

    Returns:
        An integer in the SendInput range 0 through 65,535.

    Raises:
        ValueError: The coordinate is outside the desktop or cannot be
            represented precisely by the absolute-input coordinate space.
    """
    if not 1 <= extent <= ABSOLUTE_RANGE:
        raise ValueError("Virtual desktop exceeds absolute-input precision")
    offset = position - origin
    if not 0 <= offset < extent:
        raise ValueError("Mouse destination is outside the virtual desktop")
    # Choose an integer actually inside the pixel's interval. Rounding a
    # floating midpoint down can select the previous pixel when the desktop
    # approaches the 65,536-position precision limit.
    lower = (offset * ABSOLUTE_RANGE + extent - 1) // extent
    upper = ((offset + 1) * ABSOLUTE_RANGE + extent - 1) // extent - 1
    return (lower + upper) // 2


def desktop_accessible(api: WindowsAPI) -> bool:
    """Check that the current input desktop is the ordinary Default desktop.

    Args:
        api: Initialized Windows API bindings.

    Returns:
        True only when the input desktop opens successfully and has the
        ordinary desktop name. Locked, secure and inaccessible desktops fail
        closed. The handle is always closed, and no desktop is switched.
    """
    desktop = api.user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
    if not desktop:
        return False
    try:
        name = ctypes.create_unicode_buffer(256)
        needed = DWORD()
        if not api.user32.GetUserObjectInformationW(
            desktop, UOI_NAME, name, ctypes.sizeof(name), ctypes.byref(needed)
        ):
            return False
        return name.value.casefold() == "default"
    finally:
        api.user32.CloseDesktop(desktop)


def set_process_dpi_awareness() -> None:
    """Set Per Monitor V2 before Tk creates any windows.

    Returns:
        None. Access denied is accepted when an executable manifest has already
        selected DPI awareness; the build supplies a Per Monitor V2 manifest.

    Raises:
        OSError: Windows rejects the request for another reason.
    """
    api = WindowsAPI()
    if not api.user32.SetProcessDpiAwarenessContext(-4):
        error_code = ctypes.get_last_error()
        if error_code != 5:
            raise windows_error("SetProcessDpiAwarenessContext", error_code)


class MouseInjector:
    """Inject only marked absolute movement, with no silent cursor warping."""

    def __init__(self, marker: int) -> None:
        """Create a native input adapter.

        Args:
            marker: Process-specific nonzero unsigned 32-bit event marker,
                stored in the pointer-sized dwExtraInfo field without loss.

        Raises:
            ValueError: The marker is outside the nonzero unsigned 32-bit range.
            OSError: The process is not running on 64-bit Windows.
        """
        if not 0 < marker <= MAX_INPUT_MARKER:
            raise ValueError("Mouse event marker must be a nonzero uint32")
        self.marker: int = marker
        self.api: WindowsAPI = WindowsAPI()

    def get_position(self) -> Point:
        """Return the pointer's physical coordinates, or raise OSError."""
        point = POINT()
        if not self.api.user32.GetCursorPos(ctypes.byref(point)):
            raise windows_error("GetCursorPos")
        return int(point.x), int(point.y)

    def monitor_bounds(self, point: Point) -> Bounds:
        """Return the complete monitor containing a physical point.

        Args:
            point: Physical virtual-desktop coordinates, possibly negative.

        Returns:
            Left, top, exclusive right and exclusive bottom of the nearest
            monitor. The full monitor is used, including the taskbar area.

        Raises:
            OSError: Windows cannot supply a monitor or its geometry.
        """
        monitor = self.api.user32.MonitorFromPoint(POINT(*point), 2)
        information = MONITORINFO()
        information.cbSize = ctypes.sizeof(information)
        if not monitor or not self.api.user32.GetMonitorInfoW(
            monitor, ctypes.byref(information)
        ):
            raise windows_error("GetMonitorInfoW")
        rectangle = information.rcMonitor
        return (int(rectangle.left), int(rectangle.top), int(rectangle.right),
                int(rectangle.bottom))

    def virtual_bounds(self) -> Bounds:
        """Return physical virtual-desktop bounds; raise if unavailable."""
        left = int(self.api.user32.GetSystemMetrics(76))
        top = int(self.api.user32.GetSystemMetrics(77))
        width = int(self.api.user32.GetSystemMetrics(78))
        height = int(self.api.user32.GetSystemMetrics(79))
        if width <= 0 or height <= 0:
            raise OSError("Windows virtual desktop is unavailable")
        return left, top, left + width, top + height

    def monitors(self) -> list[Bounds]:
        """Enumerate native monitor rectangles in stable left/top order.

        Returns:
            A nonempty list of complete physical monitor rectangles.

        Raises:
            OSError: Monitor enumeration fails or yields no monitors.
        """
        rectangles: list[Bounds] = []

        def collect(monitor: int, device_context: int, rectangle_pointer:
                    ctypes.POINTER(RECT), parameter: int) -> int:
            """Collect one rectangle; no operating-system handles are kept.

            Args:
                monitor: Borrowed native monitor handle, unused.
                device_context: Borrowed device context, unused.
                rectangle_pointer: Pointer valid only during this callback.
                parameter: Caller data, unused.

            Returns:
                One to continue monitor enumeration.
            """
            rectangle = rectangle_pointer.contents
            rectangles.append((int(rectangle.left), int(rectangle.top),
                               int(rectangle.right), int(rectangle.bottom)))
            return 1

        callback = MONITORENUMPROC(collect)
        if not self.api.user32.EnumDisplayMonitors(None, None, callback, 0):
            raise windows_error("EnumDisplayMonitors")
        if not rectangles:
            raise OSError("No interactive monitors are available")
        return sorted(rectangles, key=lambda item: (item[0], item[1]))

    def buttons_pressed(self) -> bool:
        """Return whether any of the five mouse buttons is currently held."""
        return any(self.api.user32.GetAsyncKeyState(key) & 0x8000
                   for key in MOUSE_BUTTON_KEYS)

    def accessible_desktop(self) -> bool:
        """Return whether ordinary user input can reach the Default desktop."""
        return desktop_accessible(self.api)

    def move_to(self, point: Point) -> None:
        """Send one marked, absolute physical-pixel mouse movement.

        Args:
            point: Destination physical coordinates on the virtual desktop.

        Returns:
            None after Windows accepts exactly one mouse input record.

        Raises:
            OSError: A mouse button is held, the desktop is unavailable,
                SendInput is blocked, or Windows cannot supply its geometry.
            ValueError: The coordinate cannot be represented precisely.
        """
        if not self.accessible_desktop() or self.buttons_pressed():
            raise OSError("Interactive desktop is unavailable or button held")
        left, top, right, bottom = self.virtual_bounds()
        packet = INPUT()
        packet.type = 0  # INPUT_MOUSE; never construct keyboard/button events.
        packet.mi.dx = normalize_coordinate(point[0], left, right - left)
        packet.mi.dy = normalize_coordinate(point[1], top, bottom - top)
        packet.mi.dwFlags = (MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE |
                             MOUSEEVENTF_VIRTUALDESK |
                             MOUSEEVENTF_MOVE_NOCOALESCE)
        packet.mi.dwExtraInfo = self.marker
        if self.api.user32.SendInput(1, ctypes.byref(packet),
                                    ctypes.sizeof(INPUT)) != 1:
            # UIPI can block injection into a higher-integrity application
            # without providing a meaningful GetLastError value.
            raise windows_error("SendInput (possibly blocked by UIPI)")
