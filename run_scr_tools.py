# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: run_scr_tools.py
# Module Type: Source and PyInstaller entry point
# Purpose: Start the application using the system Python or frozen runtime.
# Responsibilities: Add the maintained source directory and delegate startup.
# Author: Rudolf Klusal
# License: MIT

"""Source launcher: ``py -3.14 run_scr_tools.py`` from any working folder."""

from pathlib import Path
import sys

# A source checkout deliberately needs neither installation nor a virtualenv.
# This path bootstrap must precede the module-scope application import.
SOURCE_DIRECTORY: Path = Path(__file__).resolve().parent / "src"
if SOURCE_DIRECTORY.is_dir():
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from scr_tools.app import main


if __name__ == "__main__":
    raise SystemExit(main())
