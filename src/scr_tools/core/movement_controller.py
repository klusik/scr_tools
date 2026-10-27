# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/core/movement_controller.py
# Module Type: Background cursor animation
# Purpose: Execute one cancellable, tagged native-input movement at a time.
# Responsibilities: Timed animation, user priority, exact closure and shutdown.
# Author: Rudolf Klusal
# License: MIT

"""A bounded movement worker using event-driven cancellation between frames."""

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from scr_tools.configuration import Settings
from scr_tools.core.idle_scheduler import ActivitySnapshot, ActivityTracker
from scr_tools.core.movement_paths import Bounds, Point, generate_path
from scr_tools.events import AppEvent


FRAME_RATE: int = 60
MIN_FRAME_COUNT: int = 12
MAX_FRAME_COUNT: int = 600
FINAL_CORRECTION_ATTEMPTS: int = 3
INPUT_SETTLE_SECONDS: float = 0.01
WORKER_QUEUE_WAIT_SECONDS: float = 0.25
LOGGER: logging.Logger = logging.getLogger(__name__)


class CursorProvider(Protocol):
    """Native operations required for movement; implementations never click."""

    def get_position(self) -> Point:
        """Return the current physical pointer pixel, or raise OSError."""
        ...

    def monitor_bounds(self, point: Point) -> Bounds:
        """Return exclusive physical bounds of the monitor containing point."""
        ...

    def buttons_pressed(self) -> bool:
        """Return whether any mouse button is currently held."""
        ...

    def move_to(self, point: Point) -> None:
        """Inject tagged absolute movement to point, or raise OSError."""
        ...

    def accessible_desktop(self) -> bool:
        """Return whether the unlocked, normal input desktop is available."""
        ...


@dataclass(frozen=True, slots=True)
class MovementRequest:
    """A configuration and input-generation snapshot for exactly one cycle."""

    settings: Settings
    generation: int


class MovementController:
    """Own one persistent worker and reject overlapping movement requests.

    All GUI communication uses ``events``. Cancellation never restores the
    former starting position. A native event already submitted at the instant
    hardware input arrives cannot be retracted, but no subsequent frame or
    correction is deliberately sent after cancellation is observed.
    """

    def __init__(
        self, injector: CursorProvider, activity: ActivityTracker,
        events: queue.Queue[AppEvent],
    ) -> None:
        """Start the waiting worker without performing any movement.

        Args:
            injector: Native cursor API, including the application's safety gate.
            activity: Global occurrence tracker and immediate cancellation event.
            events: Queue consumed exclusively by the GUI main thread.

        Returns:
            None.
        """
        self._injector: CursorProvider = injector
        self._activity: ActivityTracker = activity
        self._events: queue.Queue[AppEvent] = events
        self._requests: queue.Queue[MovementRequest | None] = queue.Queue(maxsize=1)
        self._stop: threading.Event = threading.Event()
        self._state_lock: threading.Lock = threading.Lock()
        self._moving: bool = False
        self._thread: threading.Thread = threading.Thread(
            target=self._run, name="SCRTools-Movement", daemon=False
        )
        self._thread.start()

    @property
    def moving(self) -> bool:
        """Return True while one request is queued or executing."""
        with self._state_lock:
            return self._moving

    def start_cycle(self, settings: Settings) -> bool:
        """Queue one cycle, including explicit tests while auto movement is off.

        Args:
            settings: Validated immutable preferences to use for this cycle.

        Returns:
            True if queued; False while busy or shutting down. Safety checks
            also run on the worker immediately before each injected event.
        """
        snapshot: ActivitySnapshot = self._activity.snapshot()
        with self._state_lock:
            if self._moving or self._stop.is_set():
                return False
            self._moving = True
            self._requests.put_nowait(MovementRequest(settings, snapshot.generation))
        return True

    def cancel(self) -> None:
        """Invalidate queued and active cycles as a safety timeline transition.

        Returns:
            None. A generation change prevents a queued worker from clearing
            cancellation in ``arm``. No injected event is treated as user input.
        """
        self._activity.reset()

    def stop(self) -> None:
        """Request worker termination without blocking the GUI thread.

        Returns:
            None. Poll ``is_alive`` while performing normal GUI event handling.
        """
        self._stop.set()
        self.cancel()
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass

    def is_alive(self) -> bool:
        """Return whether the worker still owns unfinished work."""
        return self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        """Wait for worker cleanup only after the GUI event loop has finished.

        Args:
            timeout: Maximum wait in seconds, or None to await full termination.

        Returns:
            None. With a finite timeout, inspect ``is_alive`` for completion.
            Regular GUI shutdown must poll instead of calling this method.

        Raises:
            RuntimeError: The movement worker attempts to join itself.
        """
        self._thread.join(timeout)

    def _cancelled(self, generation: int) -> bool:
        """Evaluate safety conditions without holding an input-hook lock.

        Args:
            generation: External-input generation armed for this cycle.

        Returns:
            True when cancellation, desktop loss or a held button forbids input.
        """
        return (
            self._stop.is_set()
            or self._activity.cancel_event.is_set()
            or self._activity.snapshot().generation != generation
            or not self._injector.accessible_desktop()
            or self._injector.buttons_pressed()
        )

    def _execute(self, request: MovementRequest) -> str:
        """Animate one closed path using only the supplied native injector.

        Args:
            request: Immutable configuration and request-time input generation.

        Returns:
            A movement translation key identifying completion or cancellation.

        Raises:
            OSError: Native input or position verification failed.
            ValueError: Monitor geometry cannot support a valid path.
        """
        armed: ActivitySnapshot | None = self._activity.arm(request.generation)
        if armed is None or self._cancelled(request.generation):
            return "movement.cancelled"
        starting_point: Point = self._injector.get_position()
        bounds: Bounds = self._injector.monitor_bounds(starting_point)
        frame_count: int = min(
            MAX_FRAME_COUNT,
            max(MIN_FRAME_COUNT, round(request.settings.duration_seconds * FRAME_RATE)),
        )
        points: list[Point] = generate_path(
            request.settings.pattern, starting_point, bounds,
            request.settings.distance_pixels, frame_count,
        )
        if not any(point != starting_point for point in points):
            return "movement.no_space"
        beginning: float = time.monotonic()
        for index, point in enumerate(points[1:], start=1):
            deadline: float = beginning + request.settings.duration_seconds * index / frame_count
            wait_seconds: float = max(0.0, deadline - time.monotonic())
            if self._activity.cancel_event.wait(wait_seconds):
                return "movement.cancelled"
            if self._cancelled(request.generation):
                return "movement.cancelled"
            self._injector.move_to(point)
        # Absolute mouse input has finite coordinate precision. Verify physical
        # pixels, and perform every correction through SendInput as well.
        for _attempt in range(FINAL_CORRECTION_ATTEMPTS):
            # Allow Windows to dispatch the most recently submitted event. This
            # is cancellation-aware and avoids false failures under desktop load.
            if self._activity.cancel_event.wait(INPUT_SETTLE_SECONDS):
                return "movement.cancelled"
            if self._cancelled(request.generation):
                return "movement.cancelled"
            if self._injector.get_position() == starting_point:
                return "movement.completed"
            self._injector.move_to(starting_point)
        if self._activity.cancel_event.wait(INPUT_SETTLE_SECONDS):
            return "movement.cancelled"
        if self._cancelled(request.generation):
            return "movement.cancelled"
        if self._injector.get_position() != starting_point:
            raise OSError("Unable to verify the final cursor position")
        return "movement.completed"

    def _run(self) -> None:
        """Drain bounded requests and report every attempted cycle to the GUI.

        Returns:
            None after shutdown; errors are localized events and limited logs.
        """
        try:
            while not self._stop.is_set():
                try:
                    request: MovementRequest | None = self._requests.get(
                        timeout=WORKER_QUEUE_WAIT_SECONDS
                    )
                except queue.Empty:
                    continue
                if request is None or self._stop.is_set():
                    return
                key: str = "movement.failed"
                try:
                    key = self._execute(request)
                except Exception as error:
                    # Exception text can contain user-controlled paths or data.
                    LOGGER.error("Movement failed (%s)", type(error).__name__)
                finally:
                    with self._state_lock:
                        self._moving = False
                    self._events.put(AppEvent(
                        "movement_done", key,
                        {"completed": int(key == "movement.completed")},
                    ))
        finally:
            with self._state_lock:
                self._moving = False
