# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/app.py
# Module Type: Application composition and lifecycle
# Purpose: Connect native desktop services to a main-thread Tk interface.
# Responsibilities: Startup, settings transactions, scheduling, and shutdown.
# Author: Rudolf Klusal
# License: MIT

"""Composition root for the Windows-only SCR Tools application."""

from dataclasses import replace
from datetime import datetime
from functools import partial
import logging
import os
from pathlib import Path
import platform
import queue
import secrets
import struct
import sys
import sysconfig
import threading
import time
import tkinter as tk
from tkinter import messagebox
from types import TracebackType

from scr_tools.configuration import (
    ConfigurationError,
    ConfigurationStore,
    Settings,
)
from scr_tools.core.idle_scheduler import ActivityTracker, IdleScheduler
from scr_tools.core.movement_controller import MovementController
from scr_tools.core.movement_paths import Bounds, Point
from scr_tools.core.screenshot_service import ScreenshotService
from scr_tools.events import AppEvent
from scr_tools.gui.main_window import MainWindow, WindowActions
from scr_tools.localization.translator import Translator
from scr_tools.logging_setup import setup_logging
from scr_tools.resource_paths import project_resource
from scr_tools.windows.known_folders import (
    get_config_folder,
    get_log_folder,
    get_pictures_folder,
)
from scr_tools.windows.mouse_injector import (
    MouseInjector,
    set_process_dpi_awareness,
)
from scr_tools.windows.native_host import NativeHost
from scr_tools.windows.single_instance import SingleInstance
from scr_tools.windows.startup_registration import StartupRegistration


POLL_INTERVAL_MILLISECONDS: int = 100
MAX_EVENTS_PER_POLL: int = 100
TEST_SETTLE_MILLISECONDS: int = 350
INPUT_MARKER_PREFIX: int = 0x5343525400000000
LOGGER: logging.Logger = logging.getLogger(__name__)


class GuardedDesktop:
    """Compose the native cursor API with application and session readiness.

    This object is safe for background workers. It never calls Tk, and the
    last desktop check occurs immediately before each native input request.
    Windows can still change desktops between a check and its API call;
    SendInput's normal desktop and integrity boundaries remain authoritative.
    """

    def __init__(
        self,
        injector: MouseInjector,
        host: NativeHost,
        stopping: threading.Event,
        require_hooks: bool,
    ) -> None:
        """Bind one safety view to the shared native services.

        Args:
            injector (MouseInjector): Native pixel and input implementation.
            host (NativeHost): Thread-safe native readiness provider.
            stopping (threading.Event): Set before application cleanup starts.
            require_hooks (bool): True for movement, False for explicit capture.

        Returns:
            None: Native resources remain owned by their original services.
        """
        self._injector: MouseInjector = injector
        self._host: NativeHost = host
        self._stopping: threading.Event = stopping
        self._require_hooks: bool = require_hooks

    def accessible_desktop(self) -> bool:
        """Check shutdown, session, hooks where needed, and current desktop.

        Returns:
            bool: True only when the requested operation is currently allowed.
        """
        return (
            not self._stopping.is_set()
            and self._host.interactive()
            and (not self._require_hooks or self._host.hooks_ready())
            and self._injector.accessible_desktop()
        )

    def get_position(self) -> Point:
        """Return the current physical pointer coordinates.

        Returns:
            Point: Integer x/y pixels, possibly negative.

        Raises:
            OSError: Windows cannot query the pointer.
        """
        return self._injector.get_position()

    def monitor_bounds(self, point: Point) -> Bounds:
        """Return the monitor bounds associated with a physical pixel.

        Args:
            point (Point): Integer x/y pointer coordinates.

        Returns:
            Bounds: Left, top, right, bottom; right and bottom are exclusive.

        Raises:
            OSError: The display topology cannot be queried.
        """
        return self._injector.monitor_bounds(point)

    def virtual_bounds(self) -> Bounds:
        """Return the complete virtual desktop's native pixel bounds.

        Returns:
            Bounds: Exclusive right/bottom bounds spanning all monitors.

        Raises:
            OSError: Windows does not expose a usable virtual desktop.
        """
        return self._injector.virtual_bounds()

    def monitors(self) -> list[Bounds]:
        """Return physical monitor rectangles without changing their layout.

        Returns:
            list[Bounds]: Native monitor bounds in the provider's stable order.

        Raises:
            OSError: Monitor enumeration fails.
        """
        return self._injector.monitors()

    def buttons_pressed(self) -> bool:
        """Determine whether mouse-button state forbids automated movement.

        Returns:
            bool: True if a mouse button is held or the desktop is unavailable.
        """
        return (
            not self.accessible_desktop()
            or self._injector.buttons_pressed()
        )

    def move_to(self, point: Point) -> None:
        """Submit only guarded, marked mouse movement to the input stream.

        Args:
            point (Point): Target physical x/y pixel.

        Returns:
            None: The native injector checks its SendInput result.

        Raises:
            OSError: Input is unsafe or Windows rejects the operation.
        """
        if not self.accessible_desktop() or self._injector.buttons_pressed():
            raise OSError("Interactive input is unavailable")
        self._injector.move_to(point)


class Application:
    """Own the main-thread lifecycle and coordinate four background services."""

    def __init__(
        self,
        root: tk.Tk,
        store: ConfigurationStore,
        settings: Settings,
        translator: Translator,
        startup: StartupRegistration,
        initial_notices: list[str],
    ) -> None:
        """Prepare state without starting workers or mutating Tk widgets.

        Args:
            root (tk.Tk): Main-thread Tk event loop.
            store (ConfigurationStore): Per-user JSON persistence.
            settings (Settings): Validated launch preferences.
            translator (Translator): Selected language and English fallback.
            startup (StartupRegistration): Optional packaged-app Run entry.
            initial_notices (list[str]): Translation keys from startup checks.

        Returns:
            None: Call start to construct the view and start native services.
        """
        self.root: tk.Tk = root
        self.settings: Settings = settings
        self._store: ConfigurationStore = store
        self._translator: Translator = translator
        self._startup: StartupRegistration = startup
        self._initial_notices: list[str] = initial_notices
        self._events: queue.Queue[AppEvent] = queue.Queue()
        self._stopping: threading.Event = threading.Event()
        self._marker: int = INPUT_MARKER_PREFIX | secrets.randbits(32)
        self._activity: ActivityTracker = ActivityTracker(self._marker)
        self._scheduler: IdleScheduler = IdleScheduler(
            self._activity, settings.idle_seconds
        )
        self._window: MainWindow | None = None
        self._host: NativeHost | None = None
        self._movement: MovementController | None = None
        self._capture: ScreenshotService | None = None
        self._poll_id: str | None = None
        self._poll_running: bool = False
        self._test_id: str | None = None
        self._active_hotkey: str = ""
        self._hotkey_transaction: tuple[str, str] | None = None
        self._native_ready: bool = False
        self._runtime_fault: bool = False
        self._last_status_second: int = -1
        self._exit_code: int = 0

    def start(self) -> None:
        """Construct the UI, workers, and native message-pump thread.

        Returns:
            None: Scheduling proceeds through a short ordinary Tk timer.

        Raises:
            OSError: Native bindings or resources cannot be initialized.
            tk.TclError: Tk cannot build the application window.
        """
        icon_path: Path = project_resource("assets/icons/scr_tools.ico")
        self.root.report_callback_exception = self._callback_exception
        self._window = MainWindow(
            self.root,
            self._translator,
            self.settings,
            WindowActions(
                self.apply_settings,
                self.toggle_mover,
                self.test_movement,
                self.capture_now,
                self.open_screenshot_folder,
                self.hide_window,
            ),
            icon_path,
            self._startup.supported(),
        )
        self._host = NativeHost(
            self._events,
            self._activity.record_input,
            self._activity.reset,
            icon_path,
            self._translator.text,
        )
        injector: MouseInjector = MouseInjector(self._marker)
        movement_desktop: GuardedDesktop = GuardedDesktop(
            injector, self._host, self._stopping, require_hooks=True
        )
        screenshot_desktop: GuardedDesktop = GuardedDesktop(
            injector, self._host, self._stopping, require_hooks=False
        )
        self._movement = MovementController(
            movement_desktop, self._activity, self._events
        )
        self._capture = ScreenshotService(screenshot_desktop, self._events)
        self._configure_native()
        self._host.start()
        if self.settings.start_minimized:
            # The startup window remains withdrawn until native initialization
            # confirms the tray is usable. A tray failure restores it below.
            self.root.withdraw()
        else:
            self._window.show()
        if self._initial_notices:
            self._window.set_notice(
                " ".join(
                    self._translator.text(key) for key in self._initial_notices
                ),
                error=True,
            )
        self._poll_id = self.root.after(
            POLL_INTERVAL_MILLISECONDS, self._poll
        )
        LOGGER.info("Application services started")

    def _configure_native(self) -> None:
        """Queue settings on the native owner thread without blocking Tk.

        Returns:
            None: Hotkey and power results arrive as application events.
        """
        if self._host is not None:
            self._host.configure(
                self.settings.screenshot_hotkey,
                self.settings.mover_enabled and not self._runtime_fault,
                self.settings.prevent_sleep,
                self.settings.keep_displays_awake,
            )

    def _notice(self, key: str, error: bool = False) -> None:
        """Show a catalog-backed operational notice if the view is ready.

        Args:
            key (str): Translation key without sensitive exception details.
            error (bool): Whether the result indicates failure.

        Returns:
            None: Startup cleanup can safely call this before view creation.
        """
        if self._window is not None:
            self._window.set_notice(self._translator.text(key), error=error)

    def apply_settings(self) -> None:
        """Validate, persist, and apply the complete settings form.

        Returns:
            None: Failure leaves applied settings intact. An asynchronous
            hotkey conflict rolls back that field while retaining other edits.
        """
        if self._window is None or self._stopping.is_set():
            return
        if self._hotkey_transaction is not None:
            self._notice("settings.wait_hotkey")
            return
        try:
            candidate: Settings = self._window.settings_view.collect(
                self.settings
            )
        except ConfigurationError as error:
            self._notice(str(error), error=True)
            return
        previous: Settings = self.settings
        startup_changed: bool = False
        old_startup: bool = previous.start_with_windows
        try:
            if self._store.read_only:
                self._notice("configuration.future_schema", error=True)
                return
            if self._startup.supported():
                old_startup = self._startup.is_enabled()
                if old_startup != candidate.start_with_windows:
                    self._startup.set_enabled(candidate.start_with_windows)
                    startup_changed = True
            self._store.save(candidate)
        except (OSError, ConfigurationError):
            LOGGER.error("Settings transaction failed")
            if startup_changed:
                try:
                    self._startup.set_enabled(old_startup)
                except OSError:
                    LOGGER.error("Startup registration rollback failed")
                    self._notice("settings.startup_rollback_failed", error=True)
                    return
            self._notice("settings.save_failed", error=True)
            return
        self.settings = candidate
        self._activity.reset()
        self._scheduler.reset()
        if previous.screenshot_hotkey != candidate.screenshot_hotkey:
            self._hotkey_transaction = (
                previous.screenshot_hotkey, candidate.screenshot_hotkey
            )
        self._configure_native()
        self._window.settings_view.load(candidate)
        self._last_status_second = -1
        self._notice(
            "settings.language_restart"
            if previous.language != candidate.language
            else "settings.applied"
        )

    def toggle_mover(self, enabled: bool) -> None:
        """Apply pause immediately, then try to persist the user's preference.

        Args:
            enabled (bool): Desired Mouse Mover state from the window or tray.

        Returns:
            None: A storage failure never prevents the user from pausing input.
        """
        if self._stopping.is_set():
            return
        self.settings = replace(self.settings, mover_enabled=enabled)
        self._activity.reset()
        self._scheduler.reset()
        self._configure_native()
        self._last_status_second = -1
        try:
            self._store.save(self.settings)
        except (OSError, ConfigurationError):
            LOGGER.error("Mover preference could not be persisted")
            self._notice("settings.session_only", error=True)

    def test_movement(self) -> None:
        """Schedule one explicit test after its triggering click has settled.

        Returns:
            None: Input during the short settle period cancels the test. The
            current edited movement settings are used without being saved.
        """
        if (
            self._window is None or self._movement is None
            or self._stopping.is_set()
        ):
            return
        if self._test_id is not None or self._movement.moving:
            self._notice("movement.busy")
            return
        if (
            self._host is None or not self._host.interactive()
            or not self._host.hooks_ready() or self._runtime_fault
        ):
            self._notice("movement.unavailable", error=True)
            return
        try:
            candidate: Settings = self._window.settings_view.collect(
                self.settings
            )
        except ConfigurationError as error:
            self._notice(str(error), error=True)
            return
        self._activity.reset()
        self._scheduler.reset()
        generation: int = self._activity.snapshot().generation
        self._notice("movement.test_wait")
        self._test_id = self.root.after(
            TEST_SETTLE_MILLISECONDS,
            partial(self._perform_test, candidate, generation),
        )

    def _perform_test(self, candidate: Settings, generation: int) -> None:
        """Start a settled explicit test only if input has remained quiet.

        Args:
            candidate (Settings): Validated snapshot captured at the click.
            generation (int): Activity generation following that click.

        Returns:
            None: A newer event or unavailable worker cancels the attempt.
        """
        self._test_id = None
        if self._stopping.is_set() or self._movement is None:
            return
        if self._activity.snapshot().generation != generation:
            self._notice("movement.cancelled")
            return
        if not self._movement.start_cycle(candidate):
            self._notice("movement.busy")

    def capture_now(self) -> None:
        """Enqueue one noninteractive capture using the applied settings.

        Returns:
            None: A bounded worker reports success or failure in the view.
        """
        if self._capture is None or self._stopping.is_set():
            return
        if self._capture.request(self.settings) and self._window is not None:
            self._window.set_capture_status(
                self._translator.text("capture.queued")
            )

    def open_screenshot_folder(self) -> None:
        """Create and open the applied folder as an explicit GUI action.

        Returns:
            None: Folder errors appear inline, without affecting capture state.
        """
        if self._stopping.is_set():
            return
        try:
            folder: Path = Path(self.settings.screenshot_folder)
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except OSError:
            LOGGER.error("Screenshot folder could not be opened")
            self._notice("capture.open_failed", error=True)

    def hide_window(self) -> None:
        """Honor X, Alt+F4, and minimize only when a live tray can restore Tk.

        Returns:
            None: An unavailable tray keeps the window visible and reports why.
        """
        if self._window is None or self._stopping.is_set():
            return
        if self._host is not None and self._host.tray_ready():
            self._window.hide()
        else:
            self._window.show()
            self._notice("native.tray_unavailable", error=True)

    def _poll(self) -> None:
        """Process queued events and check the monotonic scheduler briefly.

        Returns:
            None: The next timer is scheduled unless all workers have stopped.
        """
        self._poll_id = None
        self._poll_running = True
        try:
            keep_polling: bool = self._process_poll()
        finally:
            self._poll_running = False
        if keep_polling:
            self._poll_id = self.root.after(
                POLL_INTERVAL_MILLISECONDS, self._poll
            )

    def _process_poll(self) -> bool:
        """Run one queue/scheduler pass while protecting timer ownership.

        Returns:
            bool: False after final Tk destruction; True to schedule another
            pass. Shutdown during an event cannot create a duplicate timer.
        """
        for _ in range(MAX_EVENTS_PER_POLL):
            try:
                event: AppEvent = self._events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        if self._stopping.is_set():
            if not self.workers_alive():
                self.root.destroy()
                return False
        else:
            ready: bool = (
                self._host is not None and self._host.interactive()
                and self._host.hooks_ready() and not self._runtime_fault
            )
            self._scheduler.configure(
                self.settings.idle_seconds, self.settings.mover_enabled, ready
            )
            if (
                self._movement is not None and not self._movement.moving
                and self._test_id is None and self._scheduler.begin_cycle()
            ):
                if not self._movement.start_cycle(self.settings):
                    self._scheduler.finish_cycle()
            current_second: int = int(time.monotonic())
            if current_second != self._last_status_second:
                self._update_status()
                self._last_status_second = current_second
        return True

    def _handle_event(self, event: AppEvent) -> None:
        """Translate one worker notification into main-thread state changes.

        Args:
            event (AppEvent): Immutable operational event from a worker.

        Returns:
            None: No event handler waits for a native thread or image encoding.
        """
        if event.kind == "exit":
            self.begin_shutdown()
            return
        if self._stopping.is_set():
            return
        window: MainWindow | None = self._window
        if event.kind == "open" and window is not None:
            window.show()
        elif event.kind == "toggle":
            self.toggle_mover(not self.settings.mover_enabled)
        elif event.kind == "capture":
            self.capture_now()
        elif event.kind == "native_ready":
            self._native_ready = True
            self._activity.reset()
            if (
                window is not None and self.settings.start_minimized
                and self._host is not None and self._host.tray_ready()
            ):
                window.hide()
        elif event.kind == "native_failed":
            self._exit_code = 1
            if window is not None:
                window.show()
                messagebox.showerror(
                    self._translator.text("app.title"),
                    self._translator.text("native.host_failed"),
                    parent=self.root,
                )
            # This is fatal startup/resource failure, not a second normal Exit
            # control. A failed native host cannot leave an inaccessible app.
            self.begin_shutdown()
        elif event.kind == "tray":
            if not event.values.get("ready") and window is not None:
                window.show()
                self._notice("native.tray_unavailable", error=True)
        elif event.kind in ("session", "display"):
            self._activity.reset()
            self._scheduler.reset()
        elif event.kind == "hotkey":
            self._handle_hotkey_result(event)
        elif event.kind == "movement_done":
            self._scheduler.finish_cycle()
            if window is not None and event.values.get("completed") == 1:
                window.set_last_movement(
                    self._translator.text(
                        "status.last_movement",
                        time=datetime.now().strftime("%H:%M:%S"),
                    )
                )
            if event.key:
                self._notice(
                    event.key, error=event.key == "movement.failed"
                )
        elif event.kind in ("capture_done", "capture_failed"):
            if window is not None:
                display_values: dict[str, str | int | float] = dict(
                    event.values
                )
                if event.kind == "capture_done" and "path" in display_values:
                    display_values["path"] = Path(
                        str(display_values["path"])
                    ).name
                window.set_capture_status(
                    self._translator.text(event.key, **display_values)
                )
        elif event.kind == "error" and window is not None:
            window.set_notice(
                self._translator.text(event.key, **event.values), error=True
            )
        elif event.kind == "power" and event.values.get("success") == 0:
            self._notice("native.power_failed", error=True)
        self._last_status_second = -1

    def _handle_hotkey_result(self, event: AppEvent) -> None:
        """Keep saved shortcut preferences aligned with transactional binding.

        Args:
            event (AppEvent): Native rebind result, including the active label.

        Returns:
            None: On a conflict, the previously working shortcut stays bound.
        """
        self._active_hotkey = str(event.values.get("hotkey", ""))
        requested: str = str(event.values.get("requested", ""))
        success: bool = bool(event.values.get("success", 0))
        transaction: tuple[str, str] | None = self._hotkey_transaction
        if transaction is not None and requested == transaction[1]:
            self._hotkey_transaction = None
            if not success:
                self.settings = replace(
                    self.settings,
                    screenshot_hotkey=self._active_hotkey or transaction[0],
                )
                if self._window is not None:
                    self._window.settings_view.set_hotkey(
                        self.settings.screenshot_hotkey
                    )
                try:
                    self._store.save(self.settings)
                except (OSError, ConfigurationError):
                    LOGGER.error("Hotkey rollback could not be persisted")
                    self._notice("settings.hotkey_save_failed", error=True)
                    return
        if not success and self._window is not None:
            self._window.set_notice(
                self._translator.text(event.key, **event.values), error=True
            )

    def _update_status(self) -> None:
        """Render one status snapshot, normally at most once per second.

        Returns:
            None: The view suppresses unchanged text independently.
        """
        if self._window is None:
            return
        if not self._native_ready:
            title: str = self._translator.text("status.starting")
            detail: str = self._translator.text("status.initializing")
        elif self._runtime_fault:
            title = self._translator.text("status.paused")
            detail = self._translator.text("error.callback")
        elif self._movement is not None and self._movement.moving:
            title = self._translator.text("status.moving")
            detail = self._translator.text("status.user_priority")
        elif not self.settings.mover_enabled:
            title = self._translator.text("status.paused")
            detail = self._translator.text("status.capture_available")
        elif self._host is None or not self._host.hooks_ready():
            title = self._translator.text("status.paused")
            detail = self._translator.text("native.hooks_failed")
        elif not self._host.interactive():
            title = self._translator.text("status.paused")
            detail = self._translator.text("native.session_unavailable")
        else:
            title = self._translator.text("status.monitoring")
            detail = self._translator.text(
                "status.idle",
                elapsed=min(
                    int(self._scheduler.idle_elapsed()),
                    self.settings.idle_seconds,
                ),
                timeout=self.settings.idle_seconds,
            )
        self._window.set_status(title, detail, self.settings.mover_enabled)

    def _callback_exception(
        self,
        error_type: type[BaseException],
        error: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        """Pause automation after an unexpected Tk callback failure.

        Args:
            error_type (type[BaseException]): Exception classification to log.
            error (BaseException): Unlogged exception, potentially private.
            traceback (TracebackType | None): Unlogged callback traceback.

        Returns:
            None: The tray remains usable; restarting clears the runtime fault.
        """
        LOGGER.error("GUI callback failed: %s", error_type.__name__)
        self._runtime_fault = True
        self._activity.reset()
        self._configure_native()
        self._notice("error.callback", error=True)
        # Tk removes a callback that raised. Re-arm the queue pump so a tray
        # Exit can always be processed after a failed polling callback.
        if self._poll_id is None and not self._poll_running:
            self._poll_id = self.root.after(
                POLL_INTERVAL_MILLISECONDS, self._poll
            )

    def begin_shutdown(self) -> None:
        """Request deterministic cleanup after tray Exit or OS termination.

        Returns:
            None: The root keeps processing events until every worker exits.
            A screenshot already encoding may finish; pending captures cancel.
        """
        if self._stopping.is_set():
            return
        self._stopping.set()
        self._activity.reset()
        if self._test_id is not None:
            self.root.after_cancel(self._test_id)
            self._test_id = None
        if self._window is not None:
            self._window.set_stopping()
        if self._movement is not None:
            self._movement.stop()
        if self._capture is not None:
            self._capture.stop()
        if self._host is not None:
            self._host.stop()
        if self._poll_id is None and not self._poll_running:
            self._poll_id = self.root.after(
                POLL_INTERVAL_MILLISECONDS, self._poll
            )
        LOGGER.info("Application shutdown requested")

    def workers_alive(self) -> bool:
        """Determine whether any service still owns resources or active work.

        Returns:
            bool: True until native cleanup and both worker exits complete.
        """
        return any(
            service is not None and service.is_alive()
            for service in (self._host, self._movement, self._capture)
        )

    def finish_shutdown(self) -> None:
        """Stop and join every resource owner after the Tk event loop ends.

        Returns:
            None: All background threads have exited when this returns. This
            method must never be invoked by a Tk callback or a worker. It also
            handles an unexpected Tk loop return before a native exit event.
            An already active filesystem write may need to finish first.
        """
        self._stopping.set()
        self._activity.reset()
        services: tuple[
            MovementController | ScreenshotService | NativeHost | None, ...
        ] = (self._movement, self._capture, self._host)
        # Stop every owner before joining any one of them: native power/input
        # cleanup must not wait for an outstanding screenshot disk flush.
        for service in services:
            if service is not None:
                service.stop()
        for service in services:
            if service is not None:
                service.join()

    @property
    def exit_code(self) -> int:
        """Return zero for ordinary exit or one for a fatal host failure."""
        return self._exit_code


def runtime_supported() -> bool:
    """Check the promised runtime before creating native resources.

    Returns:
        bool: True only on Windows with 64-bit CPython 3.14. A frozen binary
        already contains that interpreter and needs no installed Python.
    """
    basic_runtime: bool = (
        sys.platform == "win32"
        and platform.python_implementation() == "CPython"
        and sys.version_info[:2] == (3, 14)
        and struct.calcsize("P") == 8
        and sysconfig.get_platform() == "win-amd64"
        and not (sysconfig.get_config_var("Py_GIL_DISABLED") or 0)
    )
    if not basic_runtime:
        return False
    return (
        sys.getwindowsversion().build >= 22000
        and (
            bool(getattr(sys, "frozen", False))
            or sys.prefix == sys.base_prefix
        )
    )


def main() -> int:
    """Launch the one permitted instance and own final process cleanup.

    Returns:
        int: Zero for ordinary exit or an existing-instance activation; one
        for an unsupported runtime, startup error, or fatal native-host failure.
    """
    translator: Translator = Translator("en")
    if not runtime_supported():
        if sys.stderr is not None:
            print(translator.text("error.runtime"), file=sys.stderr)
        return 1
    instance: SingleInstance | None = None
    application: Application | None = None
    root: tk.Tk | None = None
    try:
        set_process_dpi_awareness()
        instance = SingleInstance()
        if not instance.acquire():
            activated: bool = instance.activate_existing()
            if not activated:
                messagebox.showerror(
                    translator.text("app.title"),
                    translator.text("error.instance_activation"),
                )
            return 0 if activated else 1
        notices: list[str] = []
        try:
            setup_logging(get_log_folder())
        except OSError:
            notices.append("error.logging")
        store: ConfigurationStore = ConfigurationStore(
            get_config_folder() / "settings.json",
            get_pictures_folder() / "SCR Tools",
        )
        settings: Settings = store.load()
        notices.extend(store.notices)
        translator = Translator(settings.language)
        startup: StartupRegistration = StartupRegistration()
        if startup.supported():
            try:
                actual_startup: bool = startup.is_enabled()
                if actual_startup != settings.start_with_windows:
                    # Windows' actual registration is authoritative. Retained
                    # settings must not silently re-enable auto-start after
                    # uninstall/reinstall or an external registry change.
                    settings = replace(
                        settings, start_with_windows=actual_startup
                    )
                    if not store.read_only:
                        store.save(settings)
            except (OSError, ConfigurationError):
                notices.append("settings.startup_read_failed")
        root = tk.Tk()
        root.withdraw()
        application = Application(
            root, store, settings, translator, startup, notices
        )
        application.start()
        root.mainloop()
        return application.exit_code
    except Exception as error:
        LOGGER.error("Startup or main loop failed: %s", type(error).__name__)
        try:
            messagebox.showerror(
                translator.text("app.title"),
                translator.text("error.startup"),
                parent=root,
            )
            if application is not None and root is not None:
                application.begin_shutdown()
                root.mainloop()
        except tk.TclError:
            # Windows may destroy Tk before a queued end-session notification
            # reaches Python. The non-GUI finally below owns cleanup then.
            pass
        return 1
    finally:
        if application is not None:
            application.finish_shutdown()
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        if instance is not None:
            instance.close()
        logging.shutdown()
