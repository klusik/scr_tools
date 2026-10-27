# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_idle_scheduler.py
# Module Type: Automated tests
# Purpose: Verify monotonic idle scheduling and self-input classification.
# Responsibilities: Real event resets, recurrence, cancellation and policy state.
# Author: Rudolf Klusal
# License: MIT

"""Deterministic event-timeline tests requiring neither Windows nor real sleeps."""

import unittest

from scr_tools.core.idle_scheduler import ActivityTracker, IdleScheduler


class FakeClock:
    """A manually advanced monotonic clock measured in seconds."""

    def __init__(self) -> None:
        """Initialize at a nonzero origin to catch wall-clock assumptions."""
        self.now: float = 1_000.0

    def __call__(self) -> float:
        """Return the current fake monotonic timestamp."""
        return self.now


class IdleSchedulerTests(unittest.TestCase):
    """Verify scheduler behavior at exact boundaries and input races."""

    def setUp(self) -> None:
        """Create a tracker and scheduler sharing one fake clock."""
        self.clock: FakeClock = FakeClock()
        self.activity: ActivityTracker = ActivityTracker(123456, self.clock)
        self.scheduler: IdleScheduler = IdleScheduler(self.activity, clock=self.clock)

    def test_exact_default_and_recurring_cycle(self) -> None:
        """Exactly 100 idle seconds triggers one cycle, then restarts at finish."""
        self.clock.now += 99.999
        self.assertFalse(self.scheduler.due())
        self.clock.now += 0.001
        self.assertTrue(self.scheduler.begin_cycle())
        self.assertFalse(self.scheduler.begin_cycle())
        self.clock.now += 1.0
        self.activity.record_input(123456, True)
        self.scheduler.finish_cycle()
        self.assertEqual(self.scheduler.remaining(), 100.0)
        self.clock.now += 99.999
        self.assertFalse(self.scheduler.due())
        self.clock.now += 0.001
        self.assertTrue(self.scheduler.due())

    def test_external_input_resets_and_cancels(self) -> None:
        """Keyboard/mouse occurrences and foreign injections are all activity."""
        for extra_info, injected in (
            (0, False), (987, True), (123456, False),
            ((1 << 32) | 123456, True),
        ):
            self.activity.arm()
            self.clock.now += 90.0
            self.activity.record_input(extra_info, injected)
            self.assertTrue(self.activity.cancel_event.is_set())
            self.assertEqual(self.scheduler.remaining(), 100.0)
            self.assertFalse(self.scheduler.due())

    def test_own_injection_is_ignored_only_internally(self) -> None:
        """A tagged injected event changes neither generation nor idle time."""
        self.activity.arm()
        before = self.activity.snapshot()
        self.clock.now += 80.0
        self.activity.record_input(123456, True)
        self.assertEqual(self.activity.snapshot(), before)
        self.assertFalse(self.activity.cancel_event.is_set())
        self.assertEqual(self.scheduler.remaining(), 20.0)

    def test_input_between_request_and_arm_wins(self) -> None:
        """Arming cannot clear cancellation that arrived after request creation."""
        generation: int = self.activity.snapshot().generation
        self.activity.record_input(0, False)
        self.assertIsNone(self.activity.arm(generation))
        self.assertTrue(self.activity.cancel_event.is_set())

    def test_pause_resume_and_session_change_restart_countdown(self) -> None:
        """Disabled and noninteractive states cannot become actionable."""
        self.clock.now += 200.0
        self.scheduler.configure(100, False, True)
        self.assertFalse(self.scheduler.due())
        self.clock.now += 500.0
        self.scheduler.configure(100, True, True)
        self.assertEqual(self.scheduler.remaining(), 100.0)
        self.clock.now += 100.0
        self.scheduler.configure(100, True, False)
        self.assertFalse(self.scheduler.due())
        self.scheduler.configure(100, True, True)
        self.assertEqual(self.scheduler.remaining(), 100.0)

    def test_configured_interval_and_identical_updates(self) -> None:
        """Normal GUI polling cannot accidentally restart unchanged settings."""
        self.scheduler.configure(25, True, True)
        self.clock.now += 24.0
        self.scheduler.configure(25, True, True)
        self.assertEqual(self.scheduler.remaining(), 1.0)
        self.clock.now += 1.0
        self.assertTrue(self.scheduler.due())


if __name__ == "__main__":
    unittest.main()
