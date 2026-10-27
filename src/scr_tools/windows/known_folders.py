# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/known_folders.py
# Module Type: Windows known-folder adapter
# Purpose: Respect redirected Windows Pictures and application-data folders.
# Responsibilities: Resolve known folders and free returned COM allocations.
# Author: Rudolf Klusal
# License: MIT
"""Known-folder resolution supports OneDrive and administrative redirection."""

import ctypes
from pathlib import Path
from uuid import UUID

from scr_tools.windows.native_api import GUID, WindowsAPI

PICTURES_ID: str = "33E28130-4E1E-4676-835A-98395C3BC3BB"
ROAMING_APPDATA_ID: str = "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D"
LOCAL_APPDATA_ID: str = "F1B32785-6FBA-4FCF-9D55-7B8E7F157091"
KF_FLAG_DONT_VERIFY: int = 0x4000


def _known_folder(identifier: str) -> Path:
    """Resolve one known folder without assuming a user profile layout.

    Args:
        identifier: String representation of a documented KNOWNFOLDERID.

    Returns:
        The absolute directory currently configured by Windows, even if it
        needs to be created. Redirection is still resolved by the OS.

    Raises:
        OSError: Windows rejects the query or returns an empty directory.
    """
    api = WindowsAPI()
    folder_id = GUID.from_buffer_copy(UUID(identifier).bytes_le)
    output = ctypes.c_wchar_p()
    result = api.shell32.SHGetKnownFolderPath(
        ctypes.byref(folder_id), KF_FLAG_DONT_VERIFY, None, ctypes.byref(output)
    )
    try:
        if result < 0 or not output.value:
            raise OSError(f"SHGetKnownFolderPath failed (HRESULT {result:#x})")
        return Path(output.value)
    finally:
        if output:
            api.ole32.CoTaskMemFree(ctypes.cast(output, ctypes.c_void_p))


def get_pictures_folder() -> Path:
    """Return the actual Pictures folder without creating subdirectories."""
    return _known_folder(PICTURES_ID)


def get_config_folder() -> Path:
    """Return the SCR Tools directory below Windows Roaming AppData."""
    return _known_folder(ROAMING_APPDATA_ID) / "SCR Tools"


def get_log_folder() -> Path:
    """Return the SCR Tools logs directory below Windows Local AppData."""
    return _known_folder(LOCAL_APPDATA_ID) / "SCR Tools" / "logs"
