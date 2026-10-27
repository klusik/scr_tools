# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/native_host.py
# Module Type: Dedicated Windows message-pump service
# Purpose: Own global input, hotkey, tray, session and power lifecycles.
# Responsibilities: Marshal commands and publish events without calling Tk.
# Author: Rudolf Klusal
# License: MIT
"""A single stable native thread owns all message-driven Windows resources."""

import ctypes
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread, get_ident

from scr_tools.events import AppEvent
from scr_tools.windows.global_hotkey import GlobalHotkey
from scr_tools.windows.input_monitor import InputMonitor
from scr_tools.windows.mouse_injector import desktop_accessible
from scr_tools.windows.native_api import (
    MSG, WINDOW_CLASS, WINDOW_TITLE, WM_ACTIVATE_INSTANCE,
    WM_COMMAND_QUEUE, WM_TRAY, WNDCLASSEXW, WNDPROC, WindowsAPI, windows_error,
)
from scr_tools.windows.power_prevention import PowerPrevention
from scr_tools.windows.session_monitor import SessionMonitor, session_connected
from scr_tools.windows.tray_icon import TrayIcon

LOGGER: logging.Logger = logging.getLogger(__name__)
WM_DESTROY: int = 0x0002
WM_CLOSE: int = 0x0010
WM_QUERYENDSESSION: int = 0x0011
WM_ENDSESSION: int = 0x0016
WM_DISPLAYCHANGE: int = 0x007E
WM_TIMER: int = 0x0113
WM_HOTKEY: int = 0x0312
WM_POWERBROADCAST: int = 0x0218
WM_WTSSESSION_CHANGE: int = 0x02B1
SESSION_TIMER_ID: int = 1
SESSION_POLL_MILLISECONDS: int = 500
DEFAULT_HOTKEY: str = "Ctrl+Shift+F11"


@dataclass(frozen=True)
class NativeConfiguration:
    """Immutable options passed from Tk to the native host thread."""

    hotkey: str = DEFAULT_HOTKEY
    mover_enabled: bool = True
    prevent_sleep: bool = True
    keep_displays_awake: bool = False


class NativeHost:
    """Manage Windows services without ever invoking a Tkinter method."""

    def __init__(self, events: Queue[AppEvent],
                 on_input: Callable[[int, bool], None],
                 on_interrupt: Callable[[], None], icon_path: Path,
                 translate: Callable[[str], str]) -> None:
        """Prepare a native host; start it separately after UI wiring.

        Args:
            events: Thread-safe outbound application event queue.
            on_input: Constant-time activity occurrence callback.
            on_interrupt: Cancel/reset callback for desktop/session changes.
            icon_path: Multi-resolution application icon resource.
            translate: Thread-safe translated-string lookup.
        """
        self._events: Queue[AppEvent] = events
        self._on_input: Callable[[int, bool], None] = on_input
        self._on_interrupt: Callable[[], None] = on_interrupt
        self._icon_path: Path = icon_path
        self._translate: Callable[[str], str] = translate
        self._commands: Queue[NativeConfiguration] = Queue()
        self._stop: Event = Event()
        self._lock: Lock = Lock()
        self._thread: Thread | None = None
        self._window: int | None = None
        self._api: WindowsAPI | None = None
        self._configuration: NativeConfiguration = NativeConfiguration()
        self._interactive: bool = False
        self._hooks_ready: bool = False
        self._tray_ready: bool = False
        self._hotkey_label: str = ""
        self._monitor: InputMonitor | None = None
        self._hotkey: GlobalHotkey | None = None
        self._power: PowerPrevention | None = None
        self._session: SessionMonitor | None = None
        self._tray: TrayIcon | None = None
        self._class_registered: bool = False
        self._session_registered: bool = False
        self._taskbar_message: int = 0
        self._instance: int | None = None
        self._window_callback = WNDPROC(self._window_procedure)
        self._power_failed: bool = False
        self._tray_failure_reported: bool = False

    def start(self) -> None:
        """Start the sole native owner thread without blocking Tk."""
        if self._thread is not None:
            raise RuntimeError("Native host cannot be started twice")
        self._thread = Thread(target=self._run, name="SCRTools-Native",
                              daemon=False)
        self._thread.start()

    def configure(self, hotkey: str, mover_enabled: bool, prevent_sleep: bool,
                  keep_displays_awake: bool) -> None:
        """Queue validated native options; registration results are events.

        Args:
            hotkey: Shortcut accepted by core.hotkey_spec.
            mover_enabled: User preference to run the activity scheduler.
            prevent_sleep: Request automatic system sleep prevention.
            keep_displays_awake: Additionally request display wakefulness.

        Returns:
            None immediately. This method never waits for the native thread.
        """
        self._commands.put(NativeConfiguration(
            hotkey, mover_enabled, prevent_sleep, keep_displays_awake
        ))
        self._wake()

    def stop(self) -> None:
        """Request deterministic cleanup without blocking Tk's event loop."""
        self._stop.set()
        self._on_interrupt()
        self._wake()

    def join(self, timeout: float | None = None) -> None:
        """Wait for native cleanup only after the GUI event loop has ended.

        This method must not run in a Tk callback or on the native owner
        thread. Request stop first, then call join from process-level cleanup
        or a test before releasing the single-instance mutex.

        Args:
            timeout: Maximum wait in seconds, or None to wait until every
                native resource has been released by its owning thread.

        Returns:
            None. An unstarted host needs no wait. After a finite timeout, use
            is_alive to determine whether cleanup has actually finished.

        Raises:
            RuntimeError: The native owner thread attempts to join itself.
        """
        thread = self._thread
        if thread is None or thread.ident is None:
            return
        if thread.ident == get_ident():
            raise RuntimeError("Native host cannot join its own owner thread")
        thread.join(timeout)

    def is_alive(self) -> bool:
        """Return whether the owner thread is still running or cleaning up."""
        return self._thread is not None and self._thread.is_alive()

    def interactive(self) -> bool:
        """Return the last checked ordinary-desktop state under a lock."""
        with self._lock:
            return self._interactive

    def hooks_ready(self) -> bool:
        """Return whether session-wide activity observation is operational."""
        with self._lock:
            return self._hooks_ready

    def tray_ready(self) -> bool:
        """Return whether hiding the UI leaves a registered tray exit path."""
        with self._lock:
            return self._tray_ready

    @property
    def hotkey(self) -> str:
        """Return the actual registered shortcut, or an empty string."""
        with self._lock:
            return self._hotkey_label

    def _wake(self) -> None:
        """Post a wake-up message when the hidden window already exists."""
        with self._lock:
            window = self._window
            api = self._api
        if window is not None and api is not None:
            api.user32.PostMessageW(window, WM_COMMAND_QUEUE, 0, 0)

    def _emit(self, kind: str, key: str = "",
              values: dict[str, str | int | float] | None = None) -> None:
        """Publish one bounded operational event for the Tk event consumer.

        Args:
            kind: Application event discriminator.
            key: Translation catalog key, or an empty key for pure actions.
            values: Small formatting/status values; no input contents.

        Returns:
            None. Values default to an empty independent dictionary.
        """
        self._events.put(AppEvent(kind, key, {} if values is None else values))

    def _run(self) -> None:
        """Create services, pump messages, and clean every resource in finally."""
        try:
            self._initialize()
            self._process_commands()
            self._emit("native_ready", values={
                "hooks": int(self.hooks_ready()),
                "tray": int(self.tray_ready()),
            })
            api = self._require_api()
            message = MSG()
            while not self._stop.is_set():
                result = api.user32.GetMessageW(
                    ctypes.byref(message), None, 0, 0
                )
                if result == -1:
                    raise windows_error("GetMessageW")
                if result == 0:
                    break
                api.user32.TranslateMessage(ctypes.byref(message))
                api.user32.DispatchMessageW(ctypes.byref(message))
        except Exception as error:
            LOGGER.error("Native Windows host failed (%s)",
                         type(error).__name__)
            self._on_interrupt()
            self._emit("native_failed", "native.host_failed")
        finally:
            self._cleanup()

    def _initialize(self) -> None:
        """Construct the hidden window and all owner-thread resources.

        Raises:
            OSError: Essential window/timer or session registration fails.
                Hook failure is reported separately and retains tray access.
        """
        api = WindowsAPI()
        with self._lock:
            self._api = api
        module = api.kernel32.GetModuleHandleW(None)
        self._instance = int(module) if module else None
        window_class = WNDCLASSEXW()
        window_class.cbSize = ctypes.sizeof(window_class)
        window_class.lpfnWndProc = self._window_callback
        window_class.hInstance = module
        window_class.lpszClassName = WINDOW_CLASS
        if not api.user32.RegisterClassExW(ctypes.byref(window_class)):
            raise windows_error("RegisterClassExW")
        self._class_registered = True
        window = api.user32.CreateWindowExW(
            0, WINDOW_CLASS, WINDOW_TITLE, 0, 0, 0, 0, 0,
            None, None, module, None
        )
        if not window:
            raise windows_error("CreateWindowExW")
        with self._lock:
            self._window = int(window)
        self._taskbar_message = int(
            api.user32.RegisterWindowMessageW("TaskbarCreated")
        )
        if not self._taskbar_message:
            raise windows_error("RegisterWindowMessageW(TaskbarCreated)")
        self._session = SessionMonitor(
            lambda: desktop_accessible(api), lambda: session_connected(api)
        )
        self._session_registered = bool(
            api.wtsapi32.WTSRegisterSessionNotification(window, 0)
        )
        if not self._session_registered:
            # Desktop probing remains conservative, but unavailable session
            # notification is a supportable error rather than silently lost.
            raise windows_error("WTSRegisterSessionNotification")
        self._power = PowerPrevention(api.kernel32.SetThreadExecutionState)
        self._hotkey = GlobalHotkey(
            lambda identifier, modifiers, key: bool(api.user32.RegisterHotKey(
                window, identifier, modifiers, key
            )),
            lambda identifier: bool(api.user32.UnregisterHotKey(
                window, identifier
            )),
        )
        self._monitor = InputMonitor(api, self._on_input)
        try:
            self._monitor.install()
        except OSError as error:
            LOGGER.error("Global input hooks could not be installed (code %s)",
                         error.errno)
            self._emit("error", "native.hooks_failed")
        with self._lock:
            self._hooks_ready = self._monitor.ready
        self._tray = TrayIcon(api, int(window), self._icon_path, self._translate)
        self._restore_tray()
        if not api.user32.SetTimer(
            window, SESSION_TIMER_ID, SESSION_POLL_MILLISECONDS, None
        ):
            raise windows_error("SetTimer(session availability)")
        # Options queued before the host started are applied before registering
        # a default binding. This avoids transient conflicts with saved options.
        if self._commands.empty():
            self._apply_configuration(self._configuration)
        else:
            self._process_commands()
        self._refresh_session(force=True)

    def _process_commands(self) -> None:
        """Apply queued settings or request message-loop termination."""
        if self._stop.is_set():
            self._require_api().user32.PostQuitMessage(0)
            return
        latest: NativeConfiguration | None = None
        while True:
            try:
                latest = self._commands.get_nowait()
            except Empty:
                break
        if latest is not None:
            self._apply_configuration(latest)

    def _apply_configuration(self, configuration: NativeConfiguration) -> None:
        """Rebind atomically, publish actual binding, then apply power policy.

        Args:
            configuration: Most recently requested native options.

        Returns:
            None. A failed hotkey retains the previous working binding.
        """
        self._configuration = configuration
        if self._hotkey is not None:
            try:
                self._hotkey.bind(configuration.hotkey)
                success = 1
                key = "native.hotkey_registered"
            except (OSError, ValueError):
                LOGGER.warning("Screenshot hotkey registration failed")
                success = 0
                key = "native.hotkey_conflict"
            with self._lock:
                self._hotkey_label = self._hotkey.label
            self._emit("hotkey", key, {
                "hotkey": self._hotkey.label,
                "requested": configuration.hotkey,
                "success": success,
            })
        self._update_power()

    def _refresh_session(self, force: bool = False) -> None:
        """Refresh the desktop guard and reset activity after transitions.

        Args:
            force: Also reset/cancel after an explicit resume/display message
                even when the measured availability did not change.

        Returns:
            None. Power is released/acquired on this same owner thread.
        """
        available = self._session is not None and self._session.interactive()
        with self._lock:
            changed = available != self._interactive
            self._interactive = available
        if changed or force:
            self._on_interrupt()
            self._emit("session", "native.session_available" if available
                       else "native.session_unavailable",
                       {"interactive": int(available)})
            self._update_power()
        if self._monitor is not None and self._monitor.callback_failed:
            self._monitor.close()
            with self._lock:
                was_ready = self._hooks_ready
                self._hooks_ready = False
            if was_ready:
                self._on_interrupt()
                self._update_power()
                self._emit("error", "native.hooks_failed")

    def _update_power(self) -> None:
        """Reconcile execution state and surface failures without dialog spam."""
        if self._power is None:
            return
        configuration = self._configuration
        try:
            active = self._power.configure(
                configuration.mover_enabled and self.hooks_ready()
                and not self._stop.is_set(),
                configuration.prevent_sleep,
                configuration.keep_displays_awake,
                self.interactive(),
            )
            self._power_failed = False
            self._emit("power", "native.power_active" if active else
                       "native.power_released",
                       {"active": int(active), "success": 1})
        except OSError as error:
            if not self._power_failed:
                LOGGER.error("Windows power requirement failed (%s)",
                             type(error).__name__)
                self._emit("power", "native.power_failed",
                           {"active": 0, "success": 0})
            self._power_failed = True

    def _restore_tray(self) -> None:
        """Retry shell registration and keep UI informed of tray availability."""
        if self._tray is None:
            return
        registered = self._tray.register()
        with self._lock:
            previously_registered = self._tray_ready
            self._tray_ready = registered
        if registered:
            if self._tray_failure_reported or not previously_registered:
                self._emit("tray", "native.tray_ready", {"ready": 1})
            self._tray_failure_reported = False
        elif not self._tray_failure_reported:
            LOGGER.warning("Tray icon unavailable; waiting for Windows Explorer")
            self._emit("tray", "native.tray_unavailable", {"ready": 0})
            self._tray_failure_reported = True

    def _window_procedure(self, window: int, message: int, first: int,
                          second: int) -> int:
        """Dispatch native messages, catching exceptions at the ABI boundary.

        Args:
            window: Hidden host HWND.
            message: Native Windows message identifier.
            first: WPARAM value.
            second: LPARAM value.

        Returns:
            Windows message result. The procedure never calls Tkinter.
        """
        try:
            return self._dispatch(window, message, first, second)
        except Exception as error:
            LOGGER.error("Native window callback failed (%s)",
                         type(error).__name__)
            self._on_interrupt()
            self._emit("error", "native.callback_failed")
            return 0

    def _dispatch(self, window: int, message: int, first: int,
                  second: int) -> int:
        """Handle host-owned messages and forward all others to Windows.

        Args:
            window: Hidden window receiving the message.
            message: Message identifier.
            first: Message-specific WPARAM.
            second: Message-specific LPARAM.

        Returns:
            A native message result compatible with DefWindowProcW.
        """
        api = self._require_api()
        if message == WM_COMMAND_QUEUE:
            self._process_commands()
            return 0
        if message == WM_ACTIVATE_INSTANCE or message == WM_CLOSE:
            # WM_CLOSE must not become another normal Exit path.
            self._emit("open")
            return 0
        if message == WM_QUERYENDSESSION:
            return 1
        if message == WM_ENDSESSION and first:
            self._on_interrupt()
            self._emit("exit", values={"os_shutdown": 1})
            self._stop.set()
            api.user32.PostQuitMessage(0)
            return 0
        if message == WM_DESTROY:
            api.user32.PostQuitMessage(0)
            return 0
        if message == WM_TIMER and first == SESSION_TIMER_ID:
            self._refresh_session()
            if self._tray is not None and not self._tray.registered:
                self._restore_tray()
            if self._power_failed:
                self._update_power()
            self._process_commands()
            return 0
        if message == self._taskbar_message and self._taskbar_message:
            if self._tray is not None:
                self._tray.registered = False
            with self._lock:
                self._tray_ready = False
            self._restore_tray()
            return 0
        if message == WM_HOTKEY:
            if self._hotkey is not None and first == self._hotkey.identifier:
                self._refresh_session()
                if self.interactive():
                    self._emit("capture")
                else:
                    self._emit("error", "native.capture_unavailable")
            return 0
        if message == WM_WTSSESSION_CHANGE:
            if self._session is not None:
                self._session.session_changed(first)
            self._refresh_session(force=True)
            return 0
        if message == WM_POWERBROADCAST:
            if self._session is not None:
                self._session.power_changed(first)
            self._refresh_session(force=True)
            return 1
        if message == WM_DISPLAYCHANGE:
            self._refresh_session(force=True)
            self._emit("display")
            return 0
        if message == WM_TRAY:
            event = second & 0xFFFF
            if event in (0x0203, 0x0400, 0x0401):
                self._emit("open")
            elif event in (0x007B, 0x0205) and self._tray is not None:
                action = self._tray.show_menu(self._configuration.mover_enabled)
                if action is not None:
                    self._emit(action)
            return 0
        return int(api.user32.DefWindowProcW(window, message, first, second))

    def _require_api(self) -> WindowsAPI:
        """Return initialized bindings or raise on a lifecycle contract error."""
        if self._api is None:
            raise RuntimeError("Native Windows API is not initialized")
        return self._api

    def _cleanup(self) -> None:
        """Release every native resource on its owning thread, even on error."""
        self._on_interrupt()
        with self._lock:
            self._interactive = False
            self._hooks_ready = False
            self._tray_ready = False
        cleanup_actions: list[tuple[str, Callable[[], None]]] = []
        if self._monitor is not None:
            cleanup_actions.append(("input hooks", self._monitor.close))
        if self._hotkey is not None:
            cleanup_actions.append(("global hotkey", self._hotkey.close))
        if self._power is not None:
            cleanup_actions.append(("power request", self._power.release))
        if self._tray is not None:
            cleanup_actions.append(("tray icon", self._tray.close))
        for description, cleanup in cleanup_actions:
            try:
                cleanup()
            except Exception as error:
                LOGGER.error("Could not release %s (%s)", description,
                             type(error).__name__)
        api = self._api
        window = self._window
        if api is not None and window is not None:
            api.user32.KillTimer(window, SESSION_TIMER_ID)
            if self._session_registered:
                api.wtsapi32.WTSUnRegisterSessionNotification(window)
            api.user32.DestroyWindow(window)
        if api is not None and self._class_registered:
            api.user32.UnregisterClassW(WINDOW_CLASS, self._instance)
        with self._lock:
            self._window = None
            self._hotkey_label = ""
