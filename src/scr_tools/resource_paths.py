# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/resource_paths.py
# Module Type: Resource location
# Purpose: Locate maintained resources in source and frozen deployments.
# Responsibilities: Resolve the icon without depending on the working folder.
# Author: Rudolf Klusal
# License: MIT

"""Resource paths used identically by source and PyInstaller launches."""

from pathlib import Path
import sys


def project_resource(relative_path: str) -> Path:
    """Return an absolute resource path, including PyInstaller extraction.

    Args:
        relative_path (str): Path beneath the project or bundle root.

    Returns:
        Path: Resource location; the caller decides whether absence is fatal.
    """
    bundle_root: str | None = getattr(sys, "_MEIPASS", None)
    root: Path = (
        Path(bundle_root)
        if bundle_root is not None
        else Path(__file__).resolve().parents[2]
    )
    return root / relative_path
