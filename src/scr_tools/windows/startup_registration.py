# Project: SCR Tools
# Repository: SCR-Tools
# File path: src/scr_tools/windows/startup_registration.py
# Module Type: Per-user Windows startup integration
# Purpose: Enable optional installed-executable startup without elevation.
# Responsibilities: Quote the executable and maintain one HKCU Run value.
# Author: Rudolf Klusal
# License: MIT
"""Auto-start is deliberately unavailable for development/source execution."""

import sys
from pathlib import Path

# winreg is Windows-only. Keeping this conditional import at module scope lets
# pure tests import platform adapters on a non-Windows verification host.
if sys.platform == "win32":
    import winreg

RUN_KEY: str = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE: str = "SCR Tools"


class StartupRegistration:
    """Maintain the installed app's per-user startup registration."""

    def supported(self) -> bool:
        """Return True only for a frozen Windows executable with a real path."""
        return (sys.platform == "win32" and
                bool(getattr(sys, "frozen", False)) and
                Path(sys.executable).is_file())

    def is_enabled(self) -> bool:
        """Check whether the current executable owns the startup value.

        Returns:
            False for unsupported source execution or a missing/mismatched
            value. Permission failures are reported as OSError.
        """
        if not self.supported():
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, value_type = winreg.QueryValueEx(key, RUN_VALUE)
            return (value_type == winreg.REG_SZ and
                    value.casefold() == self._command().casefold())
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        """Create or remove the app's HKCU startup value.

        Args:
            enabled: True to register this frozen executable, False to remove
                the SCR Tools value if present.

        Returns:
            None. Removing an absent value succeeds.

        Raises:
            OSError: Source execution is being enabled, the executable path is
                unsuitable, or Windows refuses a registry operation.
        """
        if sys.platform != "win32":
            raise OSError("Windows auto-start requires Windows")
        if enabled and not self.supported():
            raise OSError("Auto-start is available in the packaged application")
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ,
                                  self._command())
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                return

    @staticmethod
    def _command() -> str:
        """Return the fully quoted executable command, or raise OSError."""
        executable = str(Path(sys.executable).resolve())
        if '"' in executable or "\n" in executable or "\r" in executable:
            raise OSError("Executable path cannot be used in a startup command")
        return f'"{executable}"'
