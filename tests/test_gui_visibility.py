# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: tests/test_gui_visibility.py
# Module Type: Tk presentation contract tests
# Purpose: Verify temporary movement visibility with real Tk widgets.
# Responsibilities: Exercise keyboard reveal, concealment and retained edits.
# Author: Rudolf Klusal
# License: MIT

"""Real-widget checks; unavailable graphical sessions are reported as skips."""

from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock

from scr_tools.configuration import Settings
from scr_tools.gui.main_window import MainWindow, WindowActions
from scr_tools.localization.translator import Translator


class MovementVisibilityTests(unittest.TestCase):
    """Check observable presentation without native services or user settings."""

    def setUp(self) -> None:
        """Construct real widgets using nondefault in-memory preferences."""
        try:
            self.root: tk.Tk = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk graphical session unavailable: {error}")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.action: Mock = Mock()
        self.hide_action: Mock = Mock()
        self.settings: Settings = Settings(
            mover_enabled=False, idle_seconds=120, pattern="circle",
            distance_pixels=45, duration_seconds=0.5, prevent_sleep=False,
            screenshot_folder=str(Path.cwd()),
        )
        self.view: MainWindow = MainWindow(
            self.root, Translator(), self.settings,
            WindowActions(
                self.action, self.action, self.action,
                self.action, self.action, self.hide_action,
            ),
            Path("assets/icons/scr_tools.ico"), False,
        )
        self.root.update_idletasks()

    def _visible_tabs(self) -> list[str]:
        """Return captions of tabs currently exposed by the real notebook.

        Returns:
            list[str]: Visible tab captions in notebook order.
        """
        notebook: ttk.Notebook = self.view.settings_view.notebook
        return [
            str(notebook.tab(tab, "text")) for tab in notebook.tabs()
            if notebook.tab(tab, "state") != "hidden"
        ]

    def _reveal(self) -> None:
        """Deliver the reveal shortcut through Tk's real binding dispatch.

        Returns:
            None: The existing window is mapped and its mouse page is selected.
        """
        self.view.show()
        self.root.update()
        self.root.event_generate("<Control-Shift-KeyPress-S>")
        self.root.update()
        self.assertIn("Mouse Mover", self._visible_tabs())

    def test_default_window_exposes_only_screenshots_and_general(self) -> None:
        """First launch hides every movement control and selects Screenshots."""
        self.assertEqual(self._visible_tabs(), ["Screenshots", "General"])
        notebook: ttk.Notebook = self.view.settings_view.notebook
        self.assertEqual(notebook.tab(notebook.select(), "text"), "Screenshots")
        for widget in self.view._movement_widgets:
            self.assertEqual(widget.winfo_manager(), "")
        for widget in (self.view._capture, self.view._apply,
                       self.view._folder_button):
            self.assertEqual(widget.winfo_manager(), "grid")
        self.assertEqual(self.view.settings_view.collect(self.settings),
                         self.settings)
        self.action.assert_not_called()

    def test_shortcut_from_an_entry_reveals_without_editing_or_toggling(self) -> None:
        """Child focus and repeated shortcuts keep values and services intact."""
        self.view.show()
        self.root.update()
        editor = self.view.settings_view
        entry: ttk.Entry = next(
            child for child in editor._screenshot_page.winfo_children()
            if isinstance(child, ttk.Entry)
        )
        entry.focus_force()
        self.root.update()
        before: str = entry.get()
        for sequence in ("<Control-Shift-KeyPress-S>",
                         "<Control-Shift-KeyPress-s>"):
            entry.event_generate(sequence)
            self.root.update()
            self.assertIn("Mouse Mover", self._visible_tabs())
        self.assertEqual(entry.get(), before)
        self.assertEqual(editor.notebook.select(), str(editor._mouse_page))
        self.assertTrue(all(widget.winfo_ismapped()
                            for widget in self.view._movement_widgets))
        self.assertEqual(editor.collect(self.settings), self.settings)
        self.assertFalse(self.view._enabled.get())
        self.action.assert_not_called()

    def test_hide_and_restore_preserve_pending_and_applied_values(self) -> None:
        """Tray restoration conceals controls while retaining unsaved edits."""
        self._reveal()
        editor = self.view.settings_view
        editor._idle.set("321")
        editor._hotkey.set("Ctrl+Shift+F10")
        self.view.set_status("Moving", "Movement detail", False)
        self.view.set_last_movement("Last movement: 12:34:56")
        self.view.set_notice("Ordinary notice")
        self.view.set_movement_notice("Movement completed")
        self.view.set_capture_status("Screenshot result")
        self.view.hide()
        self.root.update()
        self.view.show()
        self.root.update()
        self.assertEqual(self._visible_tabs(), ["Screenshots", "General"])
        self.assertFalse(any(widget.winfo_ismapped()
                             for widget in self.view._movement_widgets))
        self.assertEqual(editor.collect(self.settings), replace(
            self.settings, idle_seconds=321, screenshot_hotkey="Ctrl+Shift+F10"
        ))
        self.assertEqual(self.view._notice.get(), "Ordinary notice")
        self.assertEqual(self.view._capture_status.get(), "Screenshot result")
        self._reveal()
        self.assertEqual(editor._idle.get(), "321")
        self.assertEqual(self.view._movement_notice.get(), "Movement completed")
        self.action.assert_not_called()

    def test_close_attempt_conceals_even_if_tray_hiding_is_declined(self) -> None:
        """The tray guard may retain access without retaining mouse controls."""
        self._reveal()
        self.view._request_hide()
        self.root.update()
        self.assertEqual(self.root.state(), "normal")
        self.assertEqual(self._visible_tabs(), ["Screenshots", "General"])
        self.hide_action.assert_called_once_with()

    def test_minimize_conceals_and_delegates_to_tray_hide(self) -> None:
        """An actual minimize event resets visibility before requesting hide."""
        self._reveal()
        self.hide_action.side_effect = self.view.hide
        self.root.iconify()
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        self.hide_action.assert_called_once_with()
        self.view.show()
        self.root.update()
        self.assertEqual(self._visible_tabs(), ["Screenshots", "General"])

    def test_direct_withdrawal_and_hidden_shortcut_cannot_reveal_controls(self) -> None:
        """Programmatic unmapping conceals without a recursive hide request."""
        self._reveal()
        self.root.withdraw()
        self.root.update()
        self.root.event_generate("<Control-Shift-KeyPress-S>")
        self.root.update()
        self.assertEqual(self._visible_tabs(), ["Screenshots", "General"])
        self.hide_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
