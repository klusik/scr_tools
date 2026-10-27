# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_movement_controller.py
# Module Type: Automated tests
# Purpose: Verify cancellation priority and physical cursor-position closure.
# Responsibilities: Tagged input, held buttons, worker lifetime and queued races.
# Author: Rudolf Klusal
# License: MIT

"""Movement-worker tests using an observable in-memory native API substitute."""

import queue
import threading
import unittest
from collections.abc import Callable
from dataclasses import replace

from scr_tools.configuration import Settings
from scr_tools.core.idle_scheduler import ActivitySnapshot, ActivityTracker
from scr_tools.core.movement_controller import MovementController
from scr_tools.core.movement_paths import Bounds, Point
from scr_tools.events import AppEvent


class FakeCursor:
    """Track injected positions while imitating tagged global input callbacks."""

    def __init__(self, activity: ActivityTracker) -> None:
        """Initialize a usable negative-origin monitor and an unchanged pointer."""
        self.activity: ActivityTracker = activity
        self.position: Point = (-100, 100)
        self.positions: list[Point] = []
        self.held: bool = False
        self.interactive: bool = True
        self.after_move: Callable[[], None] | None = None

    def get_position(self) -> Point:
        """Return the current fake physical pointer pixel."""
        return self.position

    def monitor_bounds(self, point: Point) -> Bounds:
        """Return a monitor left of the primary desktop."""
        return (-1920, 0, 0, 1080)

    def buttons_pressed(self) -> bool:
        """Return the test-controlled physical button state."""
        return self.held

    def accessible_desktop(self) -> bool:
        """Return the test-controlled secure-desktop gate."""
        return self.interactive

    def move_to(self, point: Point) -> None:
        """Record actual injection and deliver its tagged low-level occurrence."""
        self.position = point
        self.positions.append(point)
        self.activity.record_input(321, True)
        if self.after_move is not None:
            self.after_move()


class GatedActivityTracker(ActivityTracker):
    """Hold the worker immediately before atomic arming to expose queued races."""

    def __init__(self) -> None:
        """Create explicit arming barriers for a deterministic cancellation test."""
        super().__init__(321)
        self.entered: threading.Event = threading.Event()
        self.release: threading.Event = threading.Event()

    def arm(self, expected_generation: int | None = None) -> ActivitySnapshot | None:
        """Wait for test release before checking the original request generation."""
        self.entered.set()
        self.release.wait(2.0)
        return super().arm(expected_generation)


class MovementControllerTests(unittest.TestCase):
    """Check worker outcomes, injected coordinates and cleanup."""

    def setUp(self) -> None:
        """Create a non-Windows movement service with the shortest valid duration."""
        self.activity: ActivityTracker = ActivityTracker(321)
        self.cursor: FakeCursor = FakeCursor(self.activity)
        self.events: queue.Queue[AppEvent] = queue.Queue()
        self.controller: MovementController = MovementController(
            self.cursor, self.activity, self.events
        )
        self.settings: Settings = replace(Settings(), duration_seconds=0.2)

    def tearDown(self) -> None:
        """Require deterministic termination of the test's worker thread."""
        self.controller.stop()
        self.controller.join(2.0)
        self.assertFalse(self.controller.is_alive())

    def test_completed_cycle_injects_real_path_and_returns_exactly(self) -> None:
        """A complete cycle injects many positions while ignoring its own events."""
        start: Point = self.cursor.position
        generation: int = self.activity.snapshot().generation
        self.assertTrue(self.controller.start_cycle(self.settings))
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.key, "movement.completed")
        self.assertEqual(self.cursor.position, start)
        self.assertGreater(len(set(self.cursor.positions)), 4)
        self.assertEqual(self.activity.snapshot().generation, generation)
        self.assertFalse(self.controller.moving)

    def test_external_input_interrupts_without_returning_pointer(self) -> None:
        """External input after a frame prevents all later frames and corrections."""
        start: Point = self.cursor.position

        def interrupt_after_third_frame() -> None:
            """Inject one external occurrence at a deterministic movement frame."""
            if len(self.cursor.positions) == 3:
                self.activity.record_input(0, False)

        self.cursor.after_move = interrupt_after_third_frame
        self.controller.start_cycle(self.settings)
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.key, "movement.cancelled")
        self.assertEqual(len(self.cursor.positions), 3)
        self.assertNotEqual(self.cursor.position, start)

    def test_other_software_input_also_interrupts(self) -> None:
        """Accessibility or remote-tool injections are external input to this app."""

        def foreign_input() -> None:
            """Simulate another program's injected mouse occurrence."""
            self.activity.record_input(998877, True)

        self.cursor.after_move = foreign_input
        self.controller.start_cycle(self.settings)
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.key, "movement.cancelled")
        self.assertEqual(len(self.cursor.positions), 1)

    def test_held_button_and_secure_desktop_prevent_input(self) -> None:
        """A drag or inaccessible input desktop blocks even manual tests."""
        self.cursor.held = True
        self.controller.start_cycle(self.settings)
        self.assertEqual(self.events.get(timeout=2.0).key, "movement.cancelled")
        self.cursor.held = False
        self.cursor.interactive = False
        self.controller.start_cycle(self.settings)
        self.assertEqual(self.events.get(timeout=2.0).key, "movement.cancelled")
        self.assertEqual(self.cursor.positions, [])

    def test_explicit_test_is_allowed_while_automatic_mover_is_paused(self) -> None:
        """Paused automatic scheduling does not disable a deliberate Test action."""
        self.controller.start_cycle(replace(self.settings, mover_enabled=False))
        self.assertEqual(self.events.get(timeout=2.0).key, "movement.completed")

    def test_overlapping_cycles_are_rejected(self) -> None:
        """A queued or active request cannot spawn a second movement worker."""
        self.assertTrue(self.controller.start_cycle(self.settings))
        self.assertFalse(self.controller.start_cycle(self.settings))
        self.events.get(timeout=2.0)

    def test_cancel_before_arm_cannot_be_cleared(self) -> None:
        """Explicit cancellation invalidates a request before its worker arms."""
        self.controller.stop()
        self.controller.join(2.0)
        activity: GatedActivityTracker = GatedActivityTracker()
        self.cursor = FakeCursor(activity)
        self.controller = MovementController(self.cursor, activity, self.events)
        self.controller.start_cycle(self.settings)
        self.assertTrue(activity.entered.wait(1.0))
        self.controller.cancel()
        activity.release.set()
        self.assertEqual(self.events.get(timeout=2.0).key, "movement.cancelled")
        self.assertEqual(self.cursor.positions, [])


if __name__ == "__main__":
    unittest.main()
