# Project: SCR Tools
# Repository: SCR-Tools
# File path: tests/test_screenshot_service.py
# Module Type: Automated tests
# Purpose: Verify one-shot native-size captures and bounded PNG persistence.
# Responsibilities: Unique names, negative monitor origins, failures and shutdown.
# Author: Rudolf Klusal
# License: MIT

"""Screenshot behavior tested with real PNG encoding and mocked screen pixels."""

import queue
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scr_tools.configuration import Settings
from scr_tools.core.movement_paths import Bounds, Point
from scr_tools.core.screenshot_service import (
    ScreenshotService, grab_virtual_desktop, reserve_png, screenshot_stem,
)
from scr_tools.events import AppEvent


class FakeScreen:
    """Represent two equal-resolution monitors with a negative left origin."""

    def __init__(self) -> None:
        """Initialize an interactive desktop and capture occurrence counter."""
        self.interactive: bool = True
        self.capture_calls: int = 0

    def accessible_desktop(self) -> bool:
        """Return whether the fake session is currently unlocked."""
        return self.interactive

    def get_position(self) -> Point:
        """Return a pointer on the monitor left of the primary monitor."""
        return (-10, 5)

    def monitor_bounds(self, point: Point) -> Bounds:
        """Return the physical rectangle containing the fake pointer."""
        return (-30, 0, 0, 20)

    def virtual_bounds(self) -> Bounds:
        """Return the combined physical desktop dimensions."""
        return (-30, 0, 30, 20)

    def monitors(self) -> list[Bounds]:
        """Return the two physical monitor rectangles."""
        return [(-30, 0, 0, 20), (0, 0, 30, 20)]

    def capture(self) -> Image.Image:
        """Return actual RGB test pixels without accessing any desktop."""
        self.capture_calls += 1
        image: Image.Image = Image.new("RGB", (60, 20), (0, 0, 255))
        image.paste((255, 0, 0), (0, 0, 30, 20))
        return image


class ScreenshotServiceTests(unittest.TestCase):
    """Exercise explicit requests, native geometry and complete saved images."""

    def setUp(self) -> None:
        """Create a real temporary output folder and a fake screen backend."""
        self.temporary: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.directory: Path = Path(self.temporary.name)
        self.screen: FakeScreen = FakeScreen()
        self.events: queue.Queue[AppEvent] = queue.Queue()
        self.service: ScreenshotService = ScreenshotService(
            self.screen, self.events, capture=self.screen.capture
        )
        self.settings: Settings = replace(Settings(), screenshot_folder=str(self.directory))

    def tearDown(self) -> None:
        """Stop the worker before removing the temporary screenshot directory."""
        self.service.stop()
        self.service.join(2.0)
        self.assertFalse(self.service.is_alive())
        self.temporary.cleanup()

    def test_default_combined_capture_has_native_dimensions(self) -> None:
        """Startup captures nothing; one explicit request saves one full PNG."""
        self.assertEqual(self.screen.capture_calls, 0)
        self.service.request(self.settings)
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.kind, "capture_done")
        self.assertEqual(event.values["count"], 1)
        with Image.open(str(event.values["path"])) as saved:
            self.assertEqual(saved.size, (60, 20))
            self.assertEqual(saved.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(saved.getpixel((59, 19)), (0, 0, 255))
        self.assertEqual(self.screen.capture_calls, 1)

    def test_current_monitor_uses_negative_physical_origin(self) -> None:
        """The monitor under the pointer is cropped without shifting or scaling."""
        self.service.request(replace(self.settings, screenshot_mode="current"))
        event: AppEvent = self.events.get(timeout=2.0)
        with Image.open(str(event.values["path"])) as saved:
            self.assertEqual(saved.size, (30, 20))
            self.assertEqual(saved.getpixel((29, 19)), (255, 0, 0))

    def test_each_monitor_mode_uses_one_desktop_sample(self) -> None:
        """All per-monitor files derive from one instantaneous capture request."""
        self.service.request(replace(self.settings, screenshot_mode="each"))
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.values["count"], 2)
        self.assertEqual(self.screen.capture_calls, 1)
        paths: list[Path] = sorted(self.directory.glob("*.png"))
        self.assertEqual(len(paths), 2)
        for path in paths:
            with Image.open(path) as saved:
                self.assertEqual(saved.size, (30, 20))

    def test_names_are_collision_safe(self) -> None:
        """Repeated identical millisecond timestamps never overwrite captures."""
        stamp: datetime = datetime(2026, 10, 27, 7, 15, 30, 123456)
        stem: str = screenshot_stem(stamp)
        self.assertEqual(stem, "SCRTools_2026-10-27_07-15-30-123")
        paths: set[Path] = set()
        for _index in range(25):
            path, stream = reserve_png(self.directory, stem)
            stream.close()
            paths.add(path)
        self.assertEqual(len(paths), 25)

    def test_locked_session_does_not_capture(self) -> None:
        """Explicit shortcuts cannot capture a locked or inaccessible desktop."""
        self.screen.interactive = False
        self.service.request(self.settings)
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.key, "capture.unavailable")
        self.assertEqual(self.screen.capture_calls, 0)
        self.assertEqual(list(self.directory.glob("*.png")), [])

    def test_pillow_native_capture_arguments(self) -> None:
        """The production backend requests all Windows screens without resizing."""
        sample: Image.Image = Image.new("RGB", (1, 1))
        with patch("scr_tools.core.screenshot_service.ImageGrab.grab", return_value=sample) as grab:
            actual: Image.Image = grab_virtual_desktop()
            self.assertIs(actual, sample)
            grab.assert_called_once_with(all_screens=True, include_layered_windows=True)
        sample.close()

    def test_failed_png_encoding_removes_partial_file(self) -> None:
        """A write failure does not leave a misleading incomplete PNG behind."""
        with patch.object(Image.Image, "save", side_effect=OSError("storage failure")):
            with self.assertLogs("scr_tools.core.screenshot_service", level="ERROR"):
                self.service.request(self.settings)
                event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.key, "capture.failed")
        self.assertEqual(list(self.directory.glob("*.png")), [])

    def test_lock_during_capture_discards_pixels(self) -> None:
        """A session change during native capture prevents the resulting write."""
        self.service.stop()
        self.service.join(2.0)

        def locking_capture() -> Image.Image:
            """Return pixels after simulating a concurrent lock notification."""
            image: Image.Image = self.screen.capture()
            self.screen.interactive = False
            return image

        self.service = ScreenshotService(self.screen, self.events, locking_capture)
        self.service.request(self.settings)
        event: AppEvent = self.events.get(timeout=2.0)
        self.assertEqual(event.key, "capture.unavailable")
        self.assertEqual(list(self.directory.glob("*.png")), [])

    def test_saturated_queue_is_bounded_and_shutdown_discards_pending(self) -> None:
        """A slow encoder cannot create unlimited threads or queued captures."""
        self.service.stop()
        self.service.join(2.0)
        started: threading.Event = threading.Event()
        release: threading.Event = threading.Event()

        def blocked_capture() -> Image.Image:
            """Hold one native capture while the bounded input queue fills."""
            started.set()
            release.wait(2.0)
            return self.screen.capture()

        self.service = ScreenshotService(self.screen, self.events, blocked_capture)
        self.assertTrue(self.service.request(self.settings))
        self.assertTrue(started.wait(1.0))
        for _index in range(4):
            self.assertTrue(self.service.request(self.settings))
        self.assertFalse(self.service.request(self.settings))
        self.assertLessEqual(self.service.pending, 5)
        self.service.stop()
        release.set()
        self.service.join(2.0)
        self.assertEqual(self.screen.capture_calls, 1)
        self.assertEqual(list(self.directory.glob("*.png")), [])


if __name__ == "__main__":
    unittest.main()
