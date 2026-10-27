# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: tests/test_application_lifecycle.py
# Module Type: Application lifecycle contract tests
# Purpose: Verify settings, tray-only exit, and service composition without Tk.
# Responsibilities: Exercise real orchestration against explicit native mocks.
# Author: Rudolf Klusal
# License: MIT

"""Main-thread lifecycle tests; these do not claim real Windows GUI coverage."""

import ctypes
from dataclasses import replace
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import MagicMock, call, patch

from scr_tools.app import Application, GuardedDesktop
from scr_tools.configuration import ConfigurationStore, Settings
from scr_tools.core.idle_scheduler import ActivitySnapshot
from scr_tools.core.movement_controller import MovementController
from scr_tools.core.screenshot_service import ScreenshotService
from scr_tools.events import AppEvent
from scr_tools.gui.main_window import MainWindow, WindowActions
from scr_tools.gui.settings_view import SettingsView
from scr_tools.localization.translator import Translator
from scr_tools.windows.input_monitor import InputMonitor, LLMHF_INJECTED
from scr_tools.windows.mouse_injector import MouseInjector
from scr_tools.windows.native_api import DWORD, INPUT, MSLLHOOKSTRUCT
from scr_tools.windows.native_host import NativeHost
from scr_tools.windows.startup_registration import StartupRegistration


class ApplicationLifecycleTests(unittest.TestCase):
    """Check behavior observable at the application/native service boundary."""

    def setUp(self) -> None:
        """Create an application with real settings and no running workers."""
        self.directory: tempfile.TemporaryDirectory[str] = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(self.directory.cleanup)
        self.folder: Path = Path(self.directory.name)
        self.root: MagicMock = MagicMock(spec=tk.Tk)
        self.store: ConfigurationStore = ConfigurationStore(
            self.folder / "settings.json", self.folder / "pictures"
        )
        self.settings: Settings = self.store.load()
        self.startup: MagicMock = MagicMock(spec=StartupRegistration)
        self.startup.supported.return_value = False
        self.application: Application = Application(
            self.root, self.store, self.settings, Translator(), self.startup, []
        )
        self.window: MagicMock = MagicMock(spec=MainWindow)
        self.window.settings_view = MagicMock()
        self.application._window = self.window
        self.host: MagicMock = MagicMock(spec=NativeHost)
        self.host.interactive.return_value = True
        self.host.hooks_ready.return_value = True
        self.host.tray_ready.return_value = True
        self.host.is_alive.return_value = False
        self.application._host = self.host
        self.movement: MagicMock = MagicMock(spec=MovementController)
        self.movement.moving = False
        self.movement.is_alive.return_value = False
        self.application._movement = self.movement
        self.capture: MagicMock = MagicMock(spec=ScreenshotService)
        self.capture.is_alive.return_value = False
        self.application._capture = self.capture

    def test_close_hides_without_stopping_services(self) -> None:
        """A normal window-close action preserves all background services."""
        self.application.hide_window()
        self.window.hide.assert_called_once_with()
        self.host.stop.assert_not_called()
        self.assertFalse(self.application._stopping.is_set())

    def test_missing_tray_preserves_accessible_window(self) -> None:
        """Tray registration failure must not strand an invisible process."""
        self.host.tray_ready.return_value = False
        self.application.hide_window()
        self.window.show.assert_called_once_with()
        self.window.hide.assert_not_called()

    def test_pause_applies_even_if_settings_cannot_be_saved(self) -> None:
        """Storage failure cannot force an activity simulator to keep moving."""
        generation: int = self.application._activity.snapshot().generation
        with patch.object(self.store, "save", side_effect=OSError):
            self.application.toggle_mover(False)
        self.assertFalse(self.application.settings.mover_enabled)
        self.assertGreater(
            self.application._activity.snapshot().generation, generation
        )
        self.host.configure.assert_called_once_with(
            "Ctrl+Shift+F11", False, True, False
        )

    def test_future_schema_blocks_settings_transaction(self) -> None:
        """Future configuration files remain untouched by an older app."""
        self.store.read_only = True
        self.window.settings_view.collect.return_value = replace(
            self.settings, idle_seconds=120
        )
        self.application.apply_settings()
        self.assertEqual(self.application.settings.idle_seconds, 100)
        self.startup.set_enabled.assert_not_called()

    def test_startup_registration_rolls_back_after_save_failure(self) -> None:
        """A failed JSON write restores the previous Run-entry state."""
        self.startup.supported.return_value = True
        self.startup.is_enabled.return_value = False
        self.window.settings_view.collect.return_value = replace(
            self.settings, start_with_windows=True
        )
        with patch.object(self.store, "save", side_effect=OSError):
            self.application.apply_settings()
        self.assertEqual(
            self.startup.set_enabled.call_args_list, [call(True), call(False)]
        )
        self.assertFalse(self.application.settings.start_with_windows)

    def test_hotkey_conflict_rolls_back_only_shortcut(self) -> None:
        """Other applied edits survive a failed asynchronous shortcut rebind."""
        self.application.settings = replace(
            self.settings, screenshot_hotkey="Ctrl+Shift+F10",
            idle_seconds=120, mover_enabled=False,
        )
        self.application._hotkey_transaction = (
            "Ctrl+Shift+F11", "Ctrl+Shift+F10"
        )
        self.application._handle_event(AppEvent(
            "hotkey", "native.hotkey_conflict",
            {"hotkey": "Ctrl+Shift+F11", "requested": "Ctrl+Shift+F10",
             "success": 0},
        ))
        restored: Settings = self.store.load()
        self.assertEqual(restored.screenshot_hotkey, "Ctrl+Shift+F11")
        self.assertEqual(restored.idle_seconds, 120)
        self.assertFalse(restored.mover_enabled)
        self.assertIsNone(self.application._hotkey_transaction)

    def test_external_activity_during_test_delay_cancels(self) -> None:
        """A test never starts using a generation older than external input."""
        generation: int = self.application._activity.snapshot().generation
        self.application._activity.record_input(0, False)
        self.application._perform_test(self.settings, generation)
        self.movement.start_cycle.assert_not_called()

    def test_explicit_test_is_allowed_while_mover_paused(self) -> None:
        """The explicit test does not require enabling recurring automation."""
        paused: Settings = replace(self.settings, mover_enabled=False)
        generation: int = self.application._activity.snapshot().generation
        self.application._perform_test(paused, generation)
        self.movement.start_cycle.assert_called_once_with(paused)

    def test_own_mouse_input_survives_hook_extra_info_round_trip(self) -> None:
        """A 32-bit hook payload must not turn our movement into cancellation."""
        with patch("scr_tools.windows.mouse_injector.WindowsAPI") as api_factory:
            injector: MouseInjector = MouseInjector(self.application._marker)
        api: MagicMock = api_factory.return_value
        api.user32.GetSystemMetrics.side_effect = (
            lambda index: {76: 0, 77: 0, 78: 1920, 79: 1080}[index]
        )
        api.user32.CallNextHookEx.return_value = 0
        monitor: InputMonitor = InputMonitor(
            injector.api, self.application._activity.record_input
        )

        def deliver_input(count: int, packets: object, size: int) -> int:
            """Loop SendInput back through the observed Windows hook boundary.

            Args:
                count: Number of INPUT records, expected to be one.
                packets: Borrowed ctypes byref object for the INPUT record.
                size: Native INPUT structure size in bytes.

            Returns:
                One accepted event after delivering only its input metadata.
            """
            self.assertEqual(count, 1)
            self.assertEqual(size, ctypes.sizeof(INPUT))
            packet: INPUT = ctypes.cast(packets, ctypes.POINTER(INPUT)).contents
            hook: MSLLHOOKSTRUCT = MSLLHOOKSTRUCT()
            # Windows 11 can retain only the low DWORD of dwExtraInfo even
            # though both ABI fields must remain pointer-sized on x64.
            hook.dwExtraInfo = DWORD(packet.mi.dwExtraInfo).value
            hook.flags = LLMHF_INJECTED
            monitor._mouse_event(0, 0x0200, ctypes.addressof(hook))
            return 1

        api.user32.SendInput.side_effect = deliver_input
        before: ActivitySnapshot | None = self.application._activity.arm()
        with (
            patch.object(injector, "accessible_desktop", return_value=True),
            patch.object(injector, "buttons_pressed", return_value=False),
        ):
            injector.move_to((100, 100))
        self.assertEqual(self.application._activity.snapshot(), before)
        self.assertFalse(self.application._activity.cancel_event.is_set())
        self.assertFalse(monitor.callback_failed)
        api.user32.CallNextHookEx.assert_called_once()

    def test_exit_event_releases_all_services_and_destroys_tk(self) -> None:
        """A tray/OS exit waits for resource owners before destroying Tk."""
        self.application._events.put(AppEvent("exit"))
        self.application._poll()
        self.host.stop.assert_called_once_with()
        self.movement.stop.assert_called_once_with()
        self.capture.stop.assert_called_once_with()
        self.root.destroy.assert_called_once_with()
        self.root.after.assert_not_called()

    def test_exit_during_poll_arms_exactly_one_cleanup_timer(self) -> None:
        """Exit inside the queue pump must not spawn duplicate timer chains."""
        self.capture.is_alive.return_value = True
        self.application._events.put(AppEvent("exit"))
        self.application._poll()
        self.root.after.assert_called_once()
        self.root.destroy.assert_not_called()

    def test_final_cleanup_stops_all_workers_before_any_join(self) -> None:
        """An unexpected GUI-loop return still releases all resource owners."""
        timeline: MagicMock = MagicMock()
        timeline.attach_mock(self.movement, "movement")
        timeline.attach_mock(self.capture, "capture")
        timeline.attach_mock(self.host, "native")
        self.application.finish_shutdown()
        self.assertEqual(timeline.mock_calls, [
            call.movement.stop(), call.capture.stop(), call.native.stop(),
            call.movement.join(), call.capture.join(), call.native.join(),
        ])
        self.assertTrue(self.application._stopping.is_set())

    def test_native_configuration_precedes_start_and_never_captures(self) -> None:
        """Saved preferences reach native startup before any default request."""
        with (
            patch("scr_tools.app.MainWindow", return_value=self.window),
            patch("scr_tools.app.NativeHost", return_value=self.host),
            patch("scr_tools.app.MouseInjector", spec=MouseInjector),
            patch("scr_tools.app.MovementController", return_value=self.movement),
            patch("scr_tools.app.ScreenshotService", return_value=self.capture),
        ):
            self.application.start()
        self.assertLess(
            self.host.mock_calls.index(call.configure(
                "Ctrl+Shift+F11", True, True, False
            )),
            self.host.mock_calls.index(call.start()),
        )
        self.capture.request.assert_not_called()
        self.movement.start_cycle.assert_not_called()

    def test_desktop_gate_checks_native_and_current_desktop(self) -> None:
        """A stale interactive snapshot cannot authorize secure-desktop input."""
        injector: MagicMock = MagicMock(spec=MouseInjector)
        injector.accessible_desktop.return_value = False
        gate: GuardedDesktop = GuardedDesktop(
            injector, self.host, self.application._stopping, True
        )
        with self.assertRaises(OSError):
            gate.move_to((10, 20))
        injector.move_to.assert_not_called()

    def test_hook_failure_blocks_movement_but_not_explicit_capture(self) -> None:
        """Explicit screenshots need desktop access but no input hook."""
        injector: MagicMock = MagicMock(spec=MouseInjector)
        injector.accessible_desktop.return_value = True
        self.host.hooks_ready.return_value = False
        movement_gate: GuardedDesktop = GuardedDesktop(
            injector, self.host, self.application._stopping, True
        )
        capture_gate: GuardedDesktop = GuardedDesktop(
            injector, self.host, self.application._stopping, False
        )
        self.assertFalse(movement_gate.accessible_desktop())
        self.assertTrue(capture_gate.accessible_desktop())

    def test_movement_events_do_not_replace_ordinary_notices(self) -> None:
        """Background results remain in the optionally visible movement area."""
        for event in (
            AppEvent("movement_done", "movement.completed", {"completed": 1}),
            AppEvent("movement_done", "movement.failed"),
            AppEvent("error", "native.hooks_failed"),
            AppEvent("power", "native.power_failed", {"success": 0}),
        ):
            with self.subTest(key=event.key):
                self.application._handle_event(event)
                self.window.set_movement_notice.assert_called_with(
                    Translator().text(event.key),
                    error=event.key != "movement.completed",
                )
        self.window.set_notice.assert_not_called()
        self.movement.stop.assert_not_called()

    def test_capture_errors_remain_visible(self) -> None:
        """Concealed movement diagnostics cannot suppress screenshot errors."""
        self.application._handle_event(
            AppEvent("error", "native.capture_unavailable")
        )
        self.window.set_notice.assert_called_once_with(
            Translator().text("native.capture_unavailable"), error=True
        )
        self.window.set_movement_notice.assert_not_called()


class WindowLifecycleTests(unittest.TestCase):
    """Exercise close/minimize routing without an actual graphical display."""

    def setUp(self) -> None:
        """Create an unrendered view with explicit action spies."""
        self.root: MagicMock = MagicMock(spec=tk.Tk)
        self.hide: MagicMock = MagicMock()
        self.other_action: MagicMock = MagicMock()
        self.view: MainWindow = object.__new__(MainWindow)
        self.view.root = self.root
        self.view._actions = WindowActions(
            self.other_action, self.other_action, self.other_action,
            self.other_action, self.other_action, self.hide,
        )
        self.view.settings_view = MagicMock(spec=SettingsView)
        self.view._movement_widgets = ()

    def test_x_and_alt_f4_delegate_to_tray_hide(self) -> None:
        """The window-close handler never destroys the application."""
        self.view._request_hide()
        self.hide.assert_called_once_with()
        self.root.destroy.assert_not_called()

    def test_minimize_delegates_to_the_same_hide_handler(self) -> None:
        """An iconic root is hidden while children and withdrawals are ignored."""
        self.root.state.return_value = "iconic"
        event: tk.Event = tk.Event()
        event.widget = self.root
        self.view._on_unmap(event)
        self.hide.assert_called_once_with()
        self.root.destroy.assert_not_called()

    def test_withdrawal_does_not_recursively_hide(self) -> None:
        """A programmatic withdrawal cannot create an unmap callback loop."""
        self.root.state.return_value = "withdrawn"
        event: tk.Event = tk.Event()
        event.widget = self.root
        self.view._on_unmap(event)
        self.hide.assert_not_called()


if __name__ == "__main__":
    unittest.main()
