# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_windows_services.py
# Module Type: Unit tests for Windows service contracts
# Purpose: Verify power, hotkey, session, input and instance failure behavior.
# Responsibilities: Exercise native boundaries through deterministic mocks.
# Author: Rudolf Klusal
# License: MIT
"""Pure mocked tests do not claim to execute actual Windows system APIs."""

import ctypes
import unittest
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

from scr_tools.events import AppEvent
from scr_tools.windows.global_hotkey import GlobalHotkey, MOD_NOREPEAT
from scr_tools.windows.input_monitor import InputMonitor
from scr_tools.windows.mouse_injector import normalize_coordinate
from scr_tools.windows.native_api import (
    DWORD, INPUT, KBDLLHOOKSTRUCT, MSLLHOOKSTRUCT, MUTEX_NAME, WM_TRAY, WindowsAPI,
)
from scr_tools.windows.native_host import (
    NativeHost, WM_CLOSE, WM_ENDSESSION, WM_HOTKEY,
)
from scr_tools.windows.power_prevention import (
    ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED, PowerPrevention,
)
from scr_tools.windows.session_monitor import (
    PBT_APMRESUMEAUTOMATIC, PBT_APMSUSPEND, SessionMonitor,
    WTS_REMOTE_CONNECT, WTS_REMOTE_DISCONNECT, WTS_SESSION_LOCK,
    WTS_SESSION_UNLOCK, session_connected,
)
from scr_tools.windows.single_instance import SingleInstance


class AbsoluteMouseCoordinateTests(unittest.TestCase):
    """Check negative-origin precision and Windows x64 ABI alignment."""

    def test_pixel_centers_round_trip_at_multiple_monitor_widths(self) -> None:
        """Every physical coordinate remains representable at common widths."""
        for extent in (1, 1280, 1920, 2560, 3840, 7680, 16384,
                       32769, 60000, 65535, 65536):
            origin = -3840
            for offset in range(extent):
                normalized = normalize_coordinate(origin + offset, origin,
                                                  extent)
                self.assertEqual((normalized * extent) // 65536, offset)

    def test_outside_and_unrepresentable_destinations_are_rejected(self) -> None:
        """Invalid geometry fails instead of quietly selecting another pixel."""
        for values in ((0, 1, 100), (100, 0, 100), (0, 0, 0), (0, 0, 65537)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize_coordinate(*values)

    def test_input_structure_has_x64_size_and_extra_information(self) -> None:
        """INPUT is 40 bytes on x64 and retains a full unsigned marker."""
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("The project targets the x64 pointer ABI")
        self.assertEqual(ctypes.sizeof(INPUT), 40)
        packet = INPUT()
        packet.mi.dwExtraInfo = 0x53435254FFFFFFFF
        self.assertEqual(packet.mi.dwExtraInfo, 0x53435254FFFFFFFF)


class PowerPreventionTests(unittest.TestCase):
    """Verify stable request flags and explicit release across transitions."""

    def test_enable_pause_resume_display_and_exit(self) -> None:
        """Effective mover state owns both system and optional display flags."""
        setter = Mock(return_value=ES_CONTINUOUS)
        power = PowerPrevention(setter)
        self.assertTrue(power.configure(True, True, False, True))
        self.assertFalse(power.configure(False, True, False, True))
        self.assertTrue(power.configure(True, True, True, True))
        self.assertFalse(power.configure(True, True, True, False))
        self.assertTrue(power.configure(True, True, False, True))
        power.release()
        self.assertEqual([call.args[0] for call in setter.call_args_list], [
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED,
            ES_CONTINUOUS,
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED,
            ES_CONTINUOUS,
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED,
            ES_CONTINUOUS,
        ])

    def test_disabled_system_setting_never_requests_only_display(self) -> None:
        """Display wakefulness does not bypass the system-power preference."""
        setter = Mock(return_value=ES_CONTINUOUS)
        power = PowerPrevention(setter)
        self.assertFalse(power.configure(True, False, True, True))
        setter.assert_not_called()

    def test_failed_request_preserves_previous_flags_for_retry(self) -> None:
        """A failed Windows request is not recorded as successful."""
        setter = Mock(side_effect=[0, ES_CONTINUOUS])
        power = PowerPrevention(setter)
        with self.assertRaises(OSError):
            power.configure(True, True, False, True)
        self.assertEqual(power.flags, ES_CONTINUOUS)
        self.assertTrue(power.configure(True, True, False, True))
        self.assertEqual(setter.call_count, 2)


class HotkeyRegistrationTests(unittest.TestCase):
    """Exercise actual transactional binding behavior, including rollback."""

    def test_rebind_registers_new_before_unregistering_old(self) -> None:
        """A replacement shortcut cannot create an unbound conflict window."""
        calls: list[tuple[str, int]] = []

        def register(identifier: int, modifiers: int, key: int) -> bool:
            """Record the native registration contract and accept the key.

            Args:
                identifier: Process-local hotkey identifier.
                modifiers: Native modifier bits including no-repeat.
                key: Native virtual-key code, unused by this fake.

            Returns:
                True to simulate an available shortcut.
            """
            self.assertTrue(modifiers & MOD_NOREPEAT)
            calls.append(("register", identifier))
            return True

        def unregister(identifier: int) -> bool:
            """Record native unregistration and report success.

            Args:
                identifier: Previously registered identifier.

            Returns:
                True to simulate successful removal.
            """
            calls.append(("unregister", identifier))
            return True

        hotkey = GlobalHotkey(register, unregister)
        hotkey.bind("Ctrl+Shift+F11")
        hotkey.bind("Ctrl+Alt+F10")
        hotkey.close()
        self.assertEqual(calls, [("register", 11), ("register", 12),
                                 ("unregister", 11), ("unregister", 12)])

    def test_conflict_keeps_old_binding_and_allows_later_recovery(self) -> None:
        """A hotkey collision must not remove the working screenshot shortcut."""
        register = Mock(side_effect=[True, False, True])
        unregister = Mock(return_value=True)
        hotkey = GlobalHotkey(register, unregister)
        original = hotkey.bind("Ctrl+Shift+F11")
        with self.assertRaises(OSError):
            hotkey.bind("Ctrl+Alt+F10")
        self.assertEqual(hotkey.label, original)
        self.assertEqual(hotkey.identifier, 11)
        unregister.assert_not_called()
        self.assertEqual(hotkey.bind("Ctrl+Alt+F10"), "Ctrl+Alt+F10")
        unregister.assert_called_once_with(11)

    def test_unchanged_binding_does_not_register_twice(self) -> None:
        """Applying unrelated preferences keeps the same native hotkey."""
        register = Mock(return_value=True)
        hotkey = GlobalHotkey(register, Mock(return_value=True))
        hotkey.bind("Ctrl+Shift+F11")
        hotkey.bind("ctrl + shift + f11")
        self.assertEqual(register.call_count, 1)

    def test_initial_conflict_has_no_fake_registered_label(self) -> None:
        """Initial conflicts are represented honestly as no active shortcut."""
        hotkey = GlobalHotkey(Mock(return_value=False), Mock(return_value=True))
        with self.assertRaises(OSError):
            hotkey.bind("Ctrl+Shift+F11")
        self.assertEqual(hotkey.label, "")
        self.assertIsNone(hotkey.identifier)


class SessionAvailabilityTests(unittest.TestCase):
    """Check lock, disconnect, suspend and secure desktop gates."""

    def test_lock_unlock_disconnect_reconnect_and_suspend_resume(self) -> None:
        """Desktop accessibility alone cannot override explicit session state."""
        session = SessionMonitor(lambda: True)
        self.assertTrue(session.interactive())
        session.session_changed(WTS_SESSION_LOCK)
        self.assertFalse(session.interactive())
        session.session_changed(WTS_SESSION_UNLOCK)
        self.assertTrue(session.interactive())
        session.session_changed(WTS_REMOTE_DISCONNECT)
        self.assertFalse(session.interactive())
        session.session_changed(WTS_REMOTE_CONNECT)
        self.assertTrue(session.interactive())
        session.power_changed(PBT_APMSUSPEND)
        self.assertFalse(session.interactive())
        session.power_changed(PBT_APMRESUMEAUTOMATIC)
        self.assertTrue(session.interactive())

    def test_native_connection_query_reads_state_and_releases_buffer(self) -> None:
        """WTS query state is decoded correctly and its native buffer is freed."""
        state = DWORD(0)
        free = Mock()

        def query(server: int | None, session: int, kind: int,
                  output: object, size: object) -> int:
            """Populate caller-owned pointer slots with a borrowed test buffer.

            Args:
                server: Current Windows server handle, expected to be None.
                session: Current-session sentinel.
                kind: Connection-state information selector.
                output: ctypes byref object for the output pointer.
                size: ctypes byref object for the returned byte count.

            Returns:
                One to represent a successful WTS query.
            """
            self.assertIsNone(server)
            self.assertEqual(session, 0xFFFFFFFF)
            self.assertEqual(kind, 8)
            ctypes.cast(output, ctypes.POINTER(ctypes.c_void_p)).contents.value = (
                ctypes.addressof(state)
            )
            ctypes.cast(size, ctypes.POINTER(DWORD)).contents.value = (
                ctypes.sizeof(state)
            )
            return 1

        api = cast(WindowsAPI, SimpleNamespace(wtsapi32=SimpleNamespace(
            WTSQuerySessionInformationW=query, WTSFreeMemory=free,
        )))
        self.assertTrue(session_connected(api))
        state.value = 4
        self.assertFalse(session_connected(api))
        self.assertEqual(free.call_count, 2)

    def test_failed_native_connection_query_fails_closed(self) -> None:
        """An unavailable WTS query cannot authorize interaction at startup."""
        free = Mock()
        api = cast(WindowsAPI, SimpleNamespace(wtsapi32=SimpleNamespace(
            WTSQuerySessionInformationW=Mock(return_value=0),
            WTSFreeMemory=free,
        )))
        self.assertFalse(session_connected(api))
        free.assert_not_called()

    def test_disconnected_startup_remains_blocked_until_query_succeeds(self) -> None:
        """A process launched after disconnect cannot assume a live session."""
        connected = Mock(side_effect=[False, False, True])
        session = SessionMonitor(lambda: True, connected)
        self.assertFalse(session.interactive())
        self.assertFalse(session.interactive())
        self.assertTrue(session.interactive())

    def test_secure_desktop_is_unavailable_even_after_unlock(self) -> None:
        """The desktop check also protects a UAC prompt with no lock event."""
        session = SessionMonitor(lambda: False)
        session.session_changed(WTS_SESSION_UNLOCK)
        self.assertFalse(session.interactive())


class InputHookContractTests(unittest.TestCase):
    """Verify metadata-only observation and unconditional hook forwarding."""

    def setUp(self) -> None:
        """Create a native hook chain fake and input occurrence recorder."""
        self.forward: Mock = Mock(return_value=314)
        api = SimpleNamespace(user32=SimpleNamespace(
            CallNextHookEx=self.forward
        ))
        self.observed: Mock = Mock()
        self.monitor: InputMonitor = InputMonitor(cast(WindowsAPI, api),
                                                 self.observed)

    def test_mouse_injection_is_observed_and_not_suppressed(self) -> None:
        """The activity layer, not the hook chain, filters SCR Tools events."""
        packet = MSLLHOOKSTRUCT()
        packet.dwExtraInfo = 12345
        packet.flags = 1
        result = self.monitor._mouse_event(0, 0x0200, ctypes.addressof(packet))
        self.observed.assert_called_once_with(12345, True)
        self.assertEqual(result, 314)
        self.forward.assert_called_once()

    def test_keyboard_observation_contains_no_key_or_scan_code(self) -> None:
        """The occurrence callback receives marker and injected status only."""
        packet = KBDLLHOOKSTRUCT()
        packet.vkCode = 65
        packet.scanCode = 30
        packet.dwExtraInfo = 88
        packet.flags = 0
        self.monitor._keyboard_event(0, 0x0100, ctypes.addressof(packet))
        self.observed.assert_called_once_with(88, False)
        self.forward.assert_called_once()

    def test_negative_hook_code_does_not_dereference_a_pointer(self) -> None:
        """Windows negative hook codes pass straight to the next hook."""
        self.assertEqual(self.monitor._mouse_event(-1, 0, 0), 314)
        self.observed.assert_not_called()
        self.forward.assert_called_once()

    def test_callback_failure_still_forwards_input_and_marks_unhealthy(self) -> None:
        """Python callback exceptions cannot block the user's input stream."""
        self.observed.side_effect = RuntimeError("test activity failure")
        packet = MSLLHOOKSTRUCT()
        self.assertEqual(self.monitor._mouse_event(
            0, 0x0200, ctypes.addressof(packet)
        ), 314)
        self.assertTrue(self.monitor.callback_failed)
        self.forward.assert_called_once()


class NativeHostLifecycleTests(unittest.TestCase):
    """Exercise native message dispatch without a Windows window station."""

    def setUp(self) -> None:
        """Prepare an unstarted host with a mocked Windows message API."""
        self.events: Queue[AppEvent] = Queue()
        self.interrupt: Mock = Mock()
        self.host: NativeHost = NativeHost(
            self.events, Mock(), self.interrupt, Path("icon.ico"), lambda key: key
        )
        api = SimpleNamespace(user32=SimpleNamespace(
            PostQuitMessage=Mock(), DefWindowProcW=Mock(return_value=0)
        ))
        self.host._api = cast(WindowsAPI, api)

    def test_join_waits_for_owner_thread_cleanup_and_handles_unstarted_host(self) -> None:
        """Process-level joining observes completion before mutex release."""
        self.host.join()
        entered = Event()
        release = Event()
        completed = Event()

        def cleanup_owner() -> None:
            """Model a native owner finishing cleanup after stop is requested."""
            entered.set()
            release.wait()
            completed.set()

        self.host._thread = Thread(target=cleanup_owner)
        self.host._thread.start()
        try:
            self.assertTrue(entered.wait(1.0))
            self.host.join(0.001)
            self.assertTrue(self.host.is_alive())
            self.assertFalse(completed.is_set())
        finally:
            release.set()
            self.host.join(1.0)
        self.assertTrue(completed.is_set())
        self.assertFalse(self.host.is_alive())

    def test_native_close_requests_open_without_stopping(self) -> None:
        """A WM_CLOSE is not a second ordinary Exit command."""
        self.host._dispatch(1, WM_CLOSE, 0, 0)
        self.assertEqual(self.events.get_nowait().kind, "open")
        self.assertFalse(self.host._stop.is_set())

    def test_tray_exit_is_published_as_an_application_command(self) -> None:
        """The tray's explicit Exit action reaches the Tk shutdown owner."""
        tray = SimpleNamespace(show_menu=Mock(return_value="exit"))
        self.host._tray = tray
        self.host._dispatch(1, WM_TRAY, 0, 0x007B)
        self.assertEqual(self.events.get_nowait().kind, "exit")

    def test_os_end_session_can_terminate_without_tray(self) -> None:
        """Windows shutdown remains permitted independently of user commands."""
        self.host._dispatch(1, WM_ENDSESSION, 1, 0)
        event = self.events.get_nowait()
        self.assertEqual(event.kind, "exit")
        self.assertEqual(event.values["os_shutdown"], 1)
        self.assertTrue(self.host._stop.is_set())

    def test_failed_hooks_never_report_ready(self) -> None:
        """Unstarted or failed monitoring must not authorize movement."""
        self.assertFalse(self.host.hooks_ready())
        self.assertFalse(self.host.interactive())
        self.assertFalse(self.host.tray_ready())


class SingleInstanceTests(unittest.TestCase):
    """Check mutex ownership decisions without inventing Windows smoke results."""

    def test_first_process_owns_slot_and_closes_handle(self) -> None:
        """First creation owns the process slot until its handle is closed."""
        kernel = SimpleNamespace(CreateMutexW=Mock(return_value=50),
                                 CloseHandle=Mock(return_value=1))
        api = SimpleNamespace(kernel32=kernel)
        with patch("scr_tools.windows.single_instance.WindowsAPI",
                   return_value=api), patch.object(
                       ctypes, "set_last_error", create=True
                   ), patch.object(ctypes, "get_last_error", return_value=0,
                                   create=True):
            instance = SingleInstance()
            self.assertTrue(instance.acquire())
            self.assertTrue(instance.acquire())
            instance.close()
        kernel.CreateMutexW.assert_called_once_with(None, False, MUTEX_NAME)
        kernel.CloseHandle.assert_called_once_with(50)
        self.assertTrue(MUTEX_NAME.startswith("Local\\"))

    def test_second_process_does_not_own_slot(self) -> None:
        """ERROR_ALREADY_EXISTS cannot produce duplicate background services."""
        kernel = SimpleNamespace(CreateMutexW=Mock(return_value=51),
                                 CloseHandle=Mock(return_value=1))
        with patch("scr_tools.windows.single_instance.WindowsAPI",
                   return_value=SimpleNamespace(kernel32=kernel)), patch.object(
                       ctypes, "set_last_error", create=True
                   ), patch.object(ctypes, "get_last_error", return_value=183,
                                   create=True):
            instance = SingleInstance()
            self.assertFalse(instance.acquire())
            instance.close()
        kernel.CloseHandle.assert_called_once_with(51)


if __name__ == "__main__":
    unittest.main()
