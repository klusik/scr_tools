# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/__main__.py
# Module Type: Module entry point
# Purpose: Support python -m scr_tools from an installed source path.
# Responsibilities: Delegate application lifecycle and preserve exit codes.
# Author: Rudolf Klusal
# License: MIT

"""Run SCR Tools through its normal entry point."""

from scr_tools.app import main


if __name__ == "__main__":
    raise SystemExit(main())
