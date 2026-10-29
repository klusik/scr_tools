# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: tests/test_gui_visibility.py
# Module Type: Tk presentation contract tests
# Purpose: Verify transient controls and retained edits with real Tk widgets.
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
        self.root.focus_force()
        self.root.update()
        self.root.event_generate("<Control-Shift-KeyPress-S>")
        self.root.update()
        self.assertIn("Advanced", self._visible_tabs())

    def test_default_window_exposes_only_screenshots_and_general(self) -> None:
        """First launch selects Screenshots and exposes its ordinary actions."""
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
            self.assertIn("Advanced", self._visible_tabs())
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
        self.view.set_status("Processing", "Operation detail", False)
        self.view.set_last_movement("Last completed: 12:34:56")
        self.view.set_notice("Ordinary notice")
        self.view.set_movement_notice("Operation completed")
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
        self.assertEqual(self.view._movement_notice.get(), "Operation completed")
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

    def test_monitor_icons_edit_pending_capture_mode_only(self) -> None:
        """Native radio buttons retain the complete settings transaction."""
        editor = self.view.settings_view
        for mode in ("current", "each", "all"):
            with self.subTest(mode=mode):
                editor._mode_controls[mode].invoke()
                candidate: Settings = editor.collect(self.settings)
                self.assertEqual(candidate.screenshot_mode, mode)
                self.assertEqual(candidate.idle_seconds, 120)
                self.assertFalse(candidate.mover_enabled)
        self.assertEqual(self.settings.screenshot_mode, "all")
        self.action.assert_not_called()

    def test_switches_support_keyboard_and_disabled_startup(self) -> None:
        """Space changes a pending switch; source-mode startup stays disabled."""
        self.view.show()
        editor = self.view.settings_view
        general: str = next(
            tab for tab in editor.notebook.tabs()
            if editor.notebook.tab(tab, "text") == "General"
        )
        editor.notebook.select(general)
        self.root.update()
        editor._minimized_control.focus_force()
        self.root.update()
        editor._minimized_control.event_generate("<KeyPress-space>")
        editor._minimized_control.event_generate("<KeyRelease-space>")
        self.root.update()
        self.assertTrue(editor.collect(self.settings).start_minimized)
        self.assertFalse(self.settings.start_minimized)
        self.assertIn("disabled", editor._startup_control.state())
        editor._startup_control.invoke()
        self.assertFalse(editor._startup.get())
        self.action.assert_not_called()

    def test_dependent_display_switch_retains_its_disabled_preference(self) -> None:
        """Changing sleep availability never discards the display preference."""
        editor = self.view.settings_view
        editor.load(replace(self.settings, keep_displays_awake=True))
        self.assertIn("disabled", editor._display_control.state())
        editor._sleep_control.invoke()
        self.assertNotIn("disabled", editor._display_control.state())
        editor._sleep_control.invoke()
        self.assertIn("disabled", editor._display_control.state())
        self.assertTrue(editor.collect(self.settings).keep_displays_awake)
        self.action.assert_not_called()

    def test_help_opens_by_keyboard_and_closes_on_escape_and_outside_click(self) -> None:
        """Long guidance is accessible without permanent paragraphs or edits."""
        self.view.show()
        self.root.update()
        help_popup = self.view.settings_view._page_help["tab.screenshots"]
        help_popup._widget.focus_force()
        self.root.update()
        help_popup._widget.event_generate("<Return>")
        self.root.update()
        self.assertIsNotNone(help_popup._popup)
        self.assertTrue(help_popup._popup.winfo_ismapped())
        help_popup._widget.event_generate("<Escape>")
        self.root.update()
        self.assertIsNone(help_popup._popup)
        help_popup.toggle()
        self.root.update()
        self.view._capture.event_generate("<ButtonPress-1>")
        self.root.update()
        self.assertIsNone(help_popup._popup)
        self.assertEqual(self.view.settings_view.collect(self.settings),
                         self.settings)
        self.action.assert_not_called()

    def test_hide_and_control_destruction_release_help_resources(self) -> None:
        """Help windows and timers cannot outlive concealed or destroyed UI."""
        self._reveal()
        help_popup = self.view.settings_view._page_help["tab.mouse"]
        help_popup.toggle()
        self.root.update()
        self.assertIsNotNone(help_popup._popup)
        self.view.hide()
        self.root.update()
        self.assertIsNone(help_popup._popup)
        self.view.show()
        self.root.update()
        help_popup._widget.destroy()
        self.assertEqual(help_popup._bindings, [])
        self.assertIsNone(help_popup._timer)
        self.assertIsNone(help_popup._popup)

    def test_initial_layout_is_compact_and_every_page_fits(self) -> None:
        """A withdrawn start must measure Screenshots instead of hidden Mouse."""
        self.view.show()
        self.root.update()
        self.assertLess(
            self.root.winfo_height(), self.view._presentation.pixels(420)
        )
        centers: list[int] = [
            button.winfo_rooty() + button.winfo_height() // 2
            for button in (self.view._capture, self.view._folder_button,
                           self.view._apply)
        ]
        self.assertLessEqual(max(centers) - min(centers), 1)
        editor = self.view.settings_view
        self._reveal()
        for tab in editor.notebook.tabs():
            with self.subTest(tab=editor.notebook.tab(tab, "text")):
                editor.notebook.select(tab)
                self.root.update()
                page: tk.Misc = editor.nametowidget(tab)
                for child in page.winfo_children():
                    if child.winfo_ismapped():
                        self.assertLessEqual(
                            child.winfo_y() + child.winfo_height(),
                            page.winfo_height(),
                        )

    def test_long_folder_shows_destination_end_without_changing_saved_path(self) -> None:
        """Clipped folder display keeps its useful suffix and full edit value."""
        self.view.show()
        self.root.update()
        folder: str = "C:\\Pictures\\" + "Archive\\" * 12 + "SCR Tools"
        editor = self.view.settings_view
        editor.load(replace(self.settings, screenshot_folder=folder))
        self.root.update()
        self.assertEqual(editor._folder_control.get(), folder)
        self.assertEqual(editor._folder_control.xview()[1], 1.0)
        self.assertEqual(editor.collect(self.settings).screenshot_folder, folder)
        self.assertNotEqual(self.settings.screenshot_folder, folder)
        self.action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
