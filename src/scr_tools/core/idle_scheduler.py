# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/core/idle_scheduler.py
# Module Type: Input timing and scheduling
# Purpose: Separate external activity from application-owned native events.
# Responsibilities: Cancellation signalling and monotonic recurring idle cycles.
# Author: Rudolf Klusal
# License: MIT

"""Thread-safe activity timestamps and a deterministic idle state machine."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from scr_tools.configuration import DEFAULT_IDLE_SECONDS


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    """External input position in the monotonic event timeline.

    Attributes:
        last_external_time: Seconds on the supplied monotonic clock.
        generation: Counter incremented for each external or session event.
    """

    last_external_time: float
    generation: int


class ActivityTracker:
    """Share only input occurrence, never key identities or typed content.

    Attributes:
        cancel_event: Wakes the background worker immediately on external input.
    """

    def __init__(
        self, marker: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Initialize the external-input clock at application startup.

        Args:
            marker: Process-specific SendInput dwExtraInfo marker.
            clock: Monotonic seconds provider, replaceable in deterministic tests.

        Returns:
            None.
        """
        self.cancel_event: threading.Event = threading.Event()
        self._marker: int = marker
        self._clock: Callable[[], float] = clock
        self._lock: threading.Lock = threading.Lock()
        self._last_external_time: float = clock()
        self._generation: int = 0

    def record_input(self, extra_info: int, injected: bool) -> None:
        """Record every input except our specifically tagged injected events.

        Args:
            extra_info: Pointer-sized dwExtraInfo value from a low-level hook.
            injected: True when the relevant native injected-input flag is set.

        Returns:
            None. External input also signals cycle cancellation.
        """
        if injected and extra_info == self._marker:
            return
        self.reset()

    def reset(self) -> None:
        """Record external activity or a safety-relevant session transition.

        Returns:
            None. Only a timestamp and generation counter are retained.
        """
        with self._lock:
            self._last_external_time = self._clock()
            self._generation += 1
            self.cancel_event.set()

    def snapshot(self) -> ActivitySnapshot:
        """Read a consistent external-input timeline position.

        Returns:
            An immutable timestamp and generation pair.
        """
        with self._lock:
            return ActivitySnapshot(self._last_external_time, self._generation)

    def arm(self, expected_generation: int | None = None) -> ActivitySnapshot | None:
        """Prepare cancellation without erasing an input-arrival race.

        Args:
            expected_generation: Generation observed when the cycle was queued.
                None permits arming at the current generation.

        Returns:
            The armed snapshot, or None if external input arrived meanwhile.
        """
        with self._lock:
            if expected_generation is not None and expected_generation != self._generation:
                return None
            self.cancel_event.clear()
            return ActivitySnapshot(self._last_external_time, self._generation)


class IdleScheduler:
    """Main-thread idle policy with an independent cycle-completion anchor.

    The scheduler owns no thread and performs no native input. Call ``due``
    from an ordinary GUI timer; successful cycles become due again one full
    idle interval after ``finish_cycle`` even though self-input is ignored.
    """

    def __init__(
        self,
        activity: ActivityTracker,
        idle_seconds: int = DEFAULT_IDLE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize enabled monitoring with a fresh countdown.

        Args:
            activity: Shared global external-input occurrence tracker.
            idle_seconds: Required inactivity interval in seconds.
            clock: The same monotonic clock used by the activity tracker.

        Returns:
            None.
        """
        self.enabled: bool = True
        self.interactive: bool = True
        self.idle_seconds: int = idle_seconds
        self._activity: ActivityTracker = activity
        self._clock: Callable[[], float] = clock
        self._anchor: float = clock()
        self._in_cycle: bool = False

    def configure(self, idle_seconds: int, enabled: bool, interactive: bool) -> None:
        """Apply policy and restart timing when its effective state changes.

        Args:
            idle_seconds: Validated inactivity threshold in seconds.
            enabled: Whether the user's background-service toggle is enabled.
            interactive: Whether hooks and the normal input desktop are ready.

        Returns:
            None. Repeated identical calls preserve the current countdown.
        """
        if (self.idle_seconds, self.enabled, self.interactive) != (
            idle_seconds, enabled, interactive
        ):
            self.idle_seconds = idle_seconds
            self.enabled = enabled
            self.interactive = interactive
            self.reset()

    def idle_elapsed(self) -> float:
        """Return inactivity measured since external input or cycle completion.

        Returns:
            Nonnegative elapsed monotonic seconds.
        """
        latest: float = max(self._anchor, self._activity.snapshot().last_external_time)
        return max(0.0, self._clock() - latest)

    def remaining(self) -> float:
        """Return seconds until the inactivity interval has elapsed.

        Returns:
            A nonnegative float; disabled state does not make it actionable.
        """
        return max(0.0, self.idle_seconds - self.idle_elapsed())

    def due(self) -> bool:
        """Determine whether exactly one new automatic cycle can begin.

        Returns:
            True only when enabled, interactive, idle and not already cycling.
        """
        return (
            self.enabled and self.interactive and not self._in_cycle
            and self.idle_elapsed() >= self.idle_seconds
        )

    def begin_cycle(self) -> bool:
        """Claim an automatic cycle without repeatedly enqueueing it.

        Returns:
            True when a due cycle was claimed; False otherwise.
        """
        if not self.due():
            return False
        self._in_cycle = True
        return True

    def finish_cycle(self) -> None:
        """Restart timing after a completed, cancelled or rejected cycle.

        Returns:
            None. This does not fabricate an external-input event.
        """
        self._in_cycle = False
        self._anchor = self._clock()

    def reset(self) -> None:
        """Start a fresh scheduling interval after a policy or session change.

        Returns:
            None. The caller separately cancels any running cycle.
        """
        self.finish_cycle()
