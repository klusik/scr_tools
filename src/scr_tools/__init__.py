# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/__init__.py
# Module Type: Package initializer
# Purpose: Expose the application version without starting background work.
# Responsibilities: Keep package imports free of native side effects.
# Author: Rudolf Klusal
# License: MIT

"""SCR Tools: an explicit desktop activity and screenshot utility."""

from scr_tools.version import VERSION

__all__: list[str] = ["VERSION"]
