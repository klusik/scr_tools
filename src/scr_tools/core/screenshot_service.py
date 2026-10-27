# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/core/screenshot_service.py
# Module Type: Background screenshot capture
# Purpose: Save explicit screenshot requests without dialogs or GUI blocking.
# Responsibilities: Bounded queuing, native pixels, unique PNGs and safe shutdown.
# Author: Rudolf Klusal
# License: MIT

"""One bounded worker for full-resolution screen capture and PNG encoding."""

import logging
import os
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from PIL import Image, ImageGrab

from scr_tools.configuration import Settings
from scr_tools.core.movement_paths import Bounds, Point
from scr_tools.events import AppEvent


MAX_CAPTURE_QUEUE: int = 4
MAX_NAME_ATTEMPTS: int = 10_000
CAPTURE_QUEUE_WAIT_SECONDS: float = 0.25
LOGGER: logging.Logger = logging.getLogger(__name__)


class ScreenProvider(Protocol):
    """Physical screen geometry and safety checks supplied by native Windows."""

    def accessible_desktop(self) -> bool:
        """Return True only for the interactive, unlocked normal input desktop."""
        ...

    def get_position(self) -> Point:
        """Return the physical pointer pixel used for current-monitor mode."""
        ...

    def monitor_bounds(self, point: Point) -> Bounds:
        """Return exclusive bounds of the monitor containing point."""
        ...

    def virtual_bounds(self) -> Bounds:
        """Return the physical virtual desktop's exclusive bounding rectangle."""
        ...

    def monitors(self) -> list[Bounds]:
        """Return current physical monitor rectangles without DPI scaling."""
        ...


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    """Explicit user intent with immutable settings and request timestamp."""

    settings: Settings
    timestamp: datetime


class CaptureUnavailableError(RuntimeError):
    """The input desktop is unavailable or changed during a capture."""


def screenshot_stem(timestamp: datetime, monitor_number: int | None = None) -> str:
    """Create the readable filename stem without touching the filesystem.

    Args:
        timestamp: Local request time, including microseconds.
        monitor_number: Optional one-based physical monitor index.

    Returns:
        A filesystem-safe SCRTools timestamp stem with millisecond precision.
    """
    stem: str = timestamp.strftime("SCRTools_%Y-%m-%d_%H-%M-%S-")
    stem += f"{timestamp.microsecond // 1000:03d}"
    if monitor_number is not None:
        stem += f"_monitor-{monitor_number:02d}"
    return stem


def reserve_png(folder: Path, stem: str) -> tuple[Path, BinaryIO]:
    """Exclusively reserve a PNG name without overwriting existing captures.

    Args:
        folder: Existing screenshot output directory.
        stem: A filename stem created by ``screenshot_stem``.

    Returns:
        The unique final path and its exclusively opened binary output stream.

    Raises:
        OSError: File creation failed or the collision limit was exhausted.
    """
    for attempt in range(MAX_NAME_ATTEMPTS):
        suffix: str = "" if attempt == 0 else f"_{attempt:03d}"
        path: Path = folder / f"{stem}{suffix}.png"
        try:
            return path, path.open("xb")
        except FileExistsError:
            continue
    raise OSError("Screenshot filename collision limit reached")


def grab_virtual_desktop() -> Image.Image:
    """Capture all Windows screens at native pixel dimensions without resizing.

    Returns:
        A Pillow RGB image of the virtual desktop, including layered windows.

    Raises:
        OSError: Windows cannot capture the desktop.
    """
    return ImageGrab.grab(all_screens=True, include_layered_windows=True)


class ScreenshotService:
    """Serialize capture and encoding work on a single bounded worker.

    Only ``request`` creates capture work. No timer or startup path captures
    pixels, and neither image bytes nor private output paths are logged.
    """

    def __init__(
        self, provider: ScreenProvider, events: queue.Queue[AppEvent],
        capture: Callable[[], Image.Image] = grab_virtual_desktop,
    ) -> None:
        """Start a worker waiting for explicit capture requests.

        Args:
            provider: Native screen geometry and session safety gate.
            events: GUI event queue for capture status only.
            capture: Native screen-capture function, replaceable for testing.

        Returns:
            None.
        """
        self._provider: ScreenProvider = provider
        self._events: queue.Queue[AppEvent] = events
        self._capture: Callable[[], Image.Image] = capture
        self._requests: queue.Queue[CaptureRequest | None] = queue.Queue(
            maxsize=MAX_CAPTURE_QUEUE
        )
        self._stop: threading.Event = threading.Event()
        self._state_lock: threading.Lock = threading.Lock()
        self._active: bool = False
        self._thread: threading.Thread = threading.Thread(
            target=self._run, name="SCRTools-Screenshots", daemon=False
        )
        self._thread.start()

    @property
    def pending(self) -> int:
        """Return queued capture count plus the currently executing request."""
        with self._state_lock:
            return self._requests.qsize() + int(self._active)

    def request(self, settings: Settings) -> bool:
        """Queue exactly one explicit user capture, rejecting queue overflow.

        Args:
            settings: Validated capture configuration at the time of the action.

        Returns:
            True when queued; False on shutdown or queue saturation, with a
            localized status event for saturation.
        """
        if self._stop.is_set():
            return False
        try:
            self._requests.put_nowait(CaptureRequest(settings, datetime.now()))
        except queue.Full:
            self._events.put(AppEvent("capture_failed", "capture.queue_full"))
            return False
        return True

    def stop(self) -> None:
        """Discard pending intent and finish or cancel current work safely.

        Returns:
            None immediately. Poll ``is_alive`` during orderly GUI shutdown.
        """
        self._stop.set()
        while True:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                break
        try:
            self._requests.put_nowait(None)
        except queue.Full:
            pass

    def is_alive(self) -> bool:
        """Return whether the screenshot worker has finished shutting down."""
        return self._thread.is_alive()

    def join(self, timeout: float | None = None) -> None:
        """Await cleanup after Tk's event loop exits or from a non-GUI test.

        Args:
            timeout: Maximum wait in seconds; None waits until active work ends.

        Returns:
            None. Inspect ``is_alive`` after a finite wait. During normal GUI
            shutdown, keep polling instead so the interface stays responsive.

        Raises:
            RuntimeError: The screenshot worker tries to join its own thread.
        """
        self._thread.join(timeout)

    def _require_interactive(self) -> None:
        """Reject unavailable or stopping desktop work at every safe boundary.

        Returns:
            None when the regular desktop is available.

        Raises:
            CaptureUnavailableError: Shutdown, locking or a secure desktop blocks
                capture. A native capture already in progress cannot be recalled.
        """
        if self._stop.is_set() or not self._provider.accessible_desktop():
            raise CaptureUnavailableError("capture.unavailable")

    def _save_image(
        self, image: Image.Image, folder: Path, timestamp: datetime,
        monitor_number: int | None,
    ) -> Path:
        """Encode one lossless PNG and remove partial output on failure.

        Args:
            image: Native-size image to encode without resampling.
            folder: Existing destination directory.
            timestamp: Original explicit capture-request time.
            monitor_number: Optional one-based per-monitor filename suffix.

        Returns:
            The completed PNG path.

        Raises:
            OSError: Creation, PNG encoding, flushing or storage failed.
            CaptureUnavailableError: The session became unavailable.
        """
        self._require_interactive()
        path, output = reserve_png(folder, screenshot_stem(timestamp, monitor_number))
        try:
            with output:
                image.save(output, format="PNG")
                output.flush()
                os.fsync(output.fileno())
            # Avoid leaving a capture whose session became unavailable while
            # PNG encoding was in progress, even though pixels were read earlier.
            self._require_interactive()
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def _execute(self, request: CaptureRequest) -> list[Path]:
        """Capture a stable desktop once and save the selected noninteractive mode.

        Args:
            request: Timestamped, explicit capture intent.

        Returns:
            Paths to completed files, in physical-monitor order when applicable.

        Raises:
            OSError: Capture, folder creation, output, or pixel validation failed.
            CaptureUnavailableError: The session or display layout changed.
        """
        self._require_interactive()
        bounds: Bounds = self._provider.virtual_bounds()
        monitors: list[Bounds] = self._provider.monitors()
        current: Bounds | None = None
        if request.settings.screenshot_mode == "current":
            current = self._provider.monitor_bounds(self._provider.get_position())
        image: Image.Image = self._capture()
        paths: list[Path] = []
        try:
            self._require_interactive()
            if bounds != self._provider.virtual_bounds() or monitors != self._provider.monitors():
                raise CaptureUnavailableError("capture.layout_changed")
            expected_size: tuple[int, int] = (bounds[2] - bounds[0], bounds[3] - bounds[1])
            if image.size != expected_size:
                raise OSError("Native screenshot dimensions do not match the virtual desktop")
            folder: Path = Path(request.settings.screenshot_folder)
            folder.mkdir(parents=True, exist_ok=True)
            if request.settings.screenshot_mode == "all":
                paths.append(self._save_image(image, folder, request.timestamp, None))
            else:
                selected: list[Bounds] = [current] if current is not None else monitors
                if not selected:
                    raise CaptureUnavailableError("capture.unavailable")
                for index, rectangle in enumerate(selected, start=1):
                    crop_box: Bounds = (
                        rectangle[0] - bounds[0], rectangle[1] - bounds[1],
                        rectangle[2] - bounds[0], rectangle[3] - bounds[1],
                    )
                    cropped: Image.Image = image.crop(crop_box)
                    try:
                        number: int | None = (
                            index if request.settings.screenshot_mode == "each"
                            else None
                        )
                        paths.append(self._save_image(cropped, folder, request.timestamp, number))
                    finally:
                        cropped.close()
            return paths
        except BaseException:
            # Treat one explicit multi-monitor request as a unit. Files from
            # older captures are never touched because every name is exclusive.
            for path in paths:
                path.unlink(missing_ok=True)
            raise
        finally:
            image.close()

    def _run(self) -> None:
        """Process bounded explicit requests and post localized completion events.

        Returns:
            None when shutdown completes. Unexpected capture failures do not
            kill the worker or expose private file paths in diagnostic logs.
        """
        while not self._stop.is_set():
            try:
                request: CaptureRequest | None = self._requests.get(
                    timeout=CAPTURE_QUEUE_WAIT_SECONDS
                )
            except queue.Empty:
                continue
            if request is None or self._stop.is_set():
                return
            with self._state_lock:
                self._active = True
            try:
                paths: list[Path] = self._execute(request)
                self._events.put(AppEvent(
                    "capture_done", "capture.saved",
                    {"path": str(paths[-1]), "count": len(paths)},
                ))
            except CaptureUnavailableError as error:
                self._events.put(AppEvent("capture_failed", str(error)))
            except Exception as error:
                LOGGER.error("Screenshot capture failed (%s)", type(error).__name__)
                self._events.put(AppEvent("capture_failed", "capture.failed"))
            finally:
                with self._state_lock:
                    self._active = False
