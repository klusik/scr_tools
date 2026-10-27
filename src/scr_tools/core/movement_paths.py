# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/core/movement_paths.py
# Module Type: Cursor path geometry
# Purpose: Build closed animated paths within one physical monitor.
# Responsibilities: Pixel-accurate closure, edge adaptation and negative origins.
# Author: Rudolf Klusal
# License: MIT

"""Pure closed-path construction in native virtual-desktop pixel coordinates."""

import math
from collections.abc import Callable


type Point = tuple[int, int]
type Bounds = tuple[int, int, int, int]
type PathFactory = Callable[[Point, Bounds, int, int], list[Point]]

MIN_PATH_STEPS: int = 12
DEFAULT_PATH_STEPS: int = 60


def _validate_geometry(start: Point, bounds: Bounds, size: int, steps: int) -> None:
    """Check the shared geometry invariants before constructing a path.

    Args:
        start: Initial physical pointer coordinates.
        bounds: Left, top, right-exclusive and bottom-exclusive monitor bounds.
        size: Requested path size in pixels.
        steps: Number of animation intervals, excluding the initial position.

    Returns:
        None.

    Raises:
        ValueError: Geometry is empty, the pointer is outside it, or size is invalid.
    """
    left, top, right, bottom = bounds
    if not left <= start[0] < right or not top <= start[1] < bottom:
        raise ValueError("movement.invalid_geometry")
    if size < 1 or steps < MIN_PATH_STEPS:
        raise ValueError("movement.invalid_geometry")


def _interpolate(first: Point, last: Point, fraction: float) -> Point:
    """Interpolate an integer position along a bounded line segment.

    Args:
        first: Beginning of the segment.
        last: End of the segment.
        fraction: Relative position between zero and one, inclusive.

    Returns:
        The nearest pixel to the interpolated point.
    """
    return (
        round(first[0] + (last[0] - first[0]) * fraction),
        round(first[1] + (last[1] - first[1]) * fraction),
    )


def rectangle_path(
    start: Point, bounds: Bounds, size: int, steps: int = DEFAULT_PATH_STEPS
) -> list[Point]:
    """Construct an inward-facing rectangle with the pointer as a corner.

    Args:
        start: Starting physical pixel, also the final returned position.
        bounds: Owning monitor bounds with exclusive right and bottom edges.
        size: Desired side length; each axis shrinks only when necessary.
        steps: Number of timed movement intervals.

    Returns:
        ``steps + 1`` points, including the initial point and exact closure.

    Raises:
        ValueError: Inputs do not satisfy the shared geometry invariants.
    """
    _validate_geometry(start, bounds, size, steps)
    left, top, right, bottom = bounds
    x, y = start
    horizontal: int = right - 1 - x if right - 1 - x >= x - left else left - x
    vertical: int = bottom - 1 - y if bottom - 1 - y >= y - top else top - y
    dx: int = min(size, abs(horizontal)) * (1 if horizontal >= 0 else -1)
    dy: int = min(size, abs(vertical)) * (1 if vertical >= 0 else -1)
    corners: list[Point] = [start, (x + dx, y), (x + dx, y + dy), (x, y + dy), start]
    points: list[Point] = [start]
    for index in range(1, steps):
        progress: float = index * 4.0 / steps
        edge: int = min(3, int(progress))
        points.append(_interpolate(corners[edge], corners[edge + 1], progress - edge))
    points.append(start)
    return points


def circle_path(
    start: Point, bounds: Bounds, size: int, steps: int = DEFAULT_PATH_STEPS
) -> list[Point]:
    """Build a circular loop, adding an inward connector at display corners.

    An exact nondegenerate circle through the extreme corner of a rectangle
    cannot remain inside that rectangle. Near such edges, a short connector
    reaches a fitted circle and retraces the connector after its closed loop.

    Args:
        start: Starting physical pixel and exact final position.
        bounds: Owning monitor bounds, permitting negative desktop coordinates.
        size: Desired circle diameter in pixels.
        steps: Number of timed movement intervals.

    Returns:
        ``steps + 1`` bounded points forming a genuinely closed circular path.

    Raises:
        ValueError: Inputs do not satisfy the shared geometry invariants.
    """
    _validate_geometry(start, bounds, size, steps)
    left, top, right, bottom = bounds
    diameter: int = min(size, right - left - 1, bottom - top - 1)
    if diameter <= 0:
        return [start] * (steps + 1)
    radius: float = diameter / 2.0
    center_x: float = min(max(start[0], left + radius), right - 1 - radius)
    center_y: float = min(max(start[1] + radius, top + radius), bottom - 1 - radius)
    angle: float = math.atan2(start[1] - center_y, start[0] - center_x)
    circle_start: Point = (
        round(center_x + radius * math.cos(angle)),
        round(center_y + radius * math.sin(angle)),
    )
    connector_steps: int = max(1, steps // 10) if circle_start != start else 0
    circle_steps: int = steps - 2 * connector_steps
    points: list[Point] = [start]
    if connector_steps:
        for index in range(1, connector_steps + 1):
            points.append(_interpolate(start, circle_start, index / connector_steps))
    for index in range(1, circle_steps + 1):
        current_angle: float = angle + math.tau * index / circle_steps
        point: Point = (
            min(right - 1, max(left, round(center_x + radius * math.cos(current_angle)))),
            min(bottom - 1, max(top, round(center_y + radius * math.sin(current_angle)))),
        )
        points.append(point)
    if connector_steps:
        for index in range(1, connector_steps + 1):
            points.append(_interpolate(circle_start, start, index / connector_steps))
    points[-1] = start
    return points


PATH_FACTORIES: dict[str, PathFactory] = {
    "rectangle": rectangle_path,
    "circle": circle_path,
}


def generate_path(
    pattern: str, start: Point, bounds: Bounds, size: int,
    steps: int = DEFAULT_PATH_STEPS,
) -> list[Point]:
    """Dispatch to an extensible named path without involving input injection.

    Args:
        pattern: Registered path name, currently rectangle or circle.
        start: Initial physical pointer coordinates.
        bounds: Owning physical monitor bounds.
        size: Desired rectangle side or circle diameter in pixels.
        steps: Number of animation intervals.

    Returns:
        A closed sequence beginning and ending at the exact start pixel.

    Raises:
        ValueError: The pattern or geometry is unsupported.
    """
    factory: PathFactory | None = PATH_FACTORIES.get(pattern)
    if factory is None:
        raise ValueError("movement.pattern_unknown")
    return factory(start, bounds, size, steps)
