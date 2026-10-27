# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/events.py
# Module Type: Thread communication contract
# Purpose: Carry operational notifications to the Tk main thread.
# Responsibilities: Define immutable, privacy-limited application events.
# Author: Rudolf Klusal
# License: MIT

"""Small application events shared by the native and portable workers."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AppEvent:
    """Describe one event without exposing GUI objects to worker threads.

    Attributes:
        kind (str): Routing name, such as ``capture_done`` or ``session``.
        key (str): English-catalog key for an optional user-visible message.
        values (dict[str, str | int | float]): Message parameters or small
            operational values. Never contains captured pixels or input keys.
    """

    kind: str
    key: str = ""
    values: dict[str, str | int | float] = field(default_factory=dict)
