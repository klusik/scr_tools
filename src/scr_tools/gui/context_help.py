# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: src/scr_tools/gui/context_help.py
# Module Type: Main-thread contextual help
# Purpose: Keep detailed guidance out of the compact settings layout.
# Responsibilities: Present keyboard-accessible help and dispose popup bindings.
# Author: Rudolf Klusal
# License: MIT

"""Click/keyboard help and short hints without workers or native resources."""

import tkinter as tk
from tkinter import ttk


HINT_DELAY_MILLISECONDS: int = 450
HELP_WRAP_PIXELS: int = 340
POPUP_OFFSET_PIXELS: int = 6
TAB_HINT_HEIGHT_PIXELS: int = 32
REFERENCE_DPI: int = 96


class ContextHelp:
    """Own one transient text popup and its Tk binding lifetimes."""

    def __init__(self, widget: tk.Widget, text: str, click: bool = False) -> None:
        """Attach translated guidance to a control on the main thread.

        Args:
            widget (tk.Widget): Control whose mouse/focus events expose help.
            text (str): Already translated explanatory or action text.
            click (bool): True for persistent question-mark help; False for hints.

        Returns:
            None: Popups are constructed lazily and destroyed with the control.
        """
        self._widget: tk.Widget = widget
        self._root: tk.Misc = widget.winfo_toplevel()
        self._text: str = text
        self._popup: tk.Toplevel | None = None
        self._timer: str | None = None
        self._anchor: tuple[int, int] | None = None
        self._bindings: list[tuple[str, str]] = []
        if not click:
            widget.bind("<Enter>", self._schedule, add="+")
            widget.bind("<Leave>", self._dismiss, add="+")
            widget.bind("<FocusIn>", self._schedule, add="+")
        widget.bind("<FocusOut>", self._dismiss, add="+")
        for sequence, callback in (
            ("<Escape>", self._dismiss),
            ("<ButtonPress>", self._outside_click),
            ("<Unmap>", self._on_unmap),
        ):
            identifier: str = self._root.bind(sequence, callback, add="+")
            self._bindings.append((sequence, identifier))
        widget.bind("<Destroy>", self._destroy, add="+")

    def _schedule(self, event: tk.Event) -> None:
        """Delay a hint so simply crossing a toolbar does not flash a popup.

        Args:
            event (tk.Event): Enter or focus event for the attached control.

        Returns:
            None: At most one hint timer is pending.
        """
        self.close()
        self._timer = self._widget.after(HINT_DELAY_MILLISECONDS, self.show)

    def show(self) -> None:
        """Display help near its control without moving keyboard focus.

        Returns:
            None: Hidden controls and an already visible popup are ignored.
        """
        self._timer = None
        if self._popup is not None or not self._widget.winfo_ismapped():
            return
        popup: tk.Toplevel = tk.Toplevel(self._widget)
        self._popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self._root)
        ttk.Label(
            popup, text=self._text, padding=(12, 10),
            wraplength=round(
                HELP_WRAP_PIXELS * self._widget.winfo_fpixels("1i")
                / REFERENCE_DPI
            ),
            relief="solid", borderwidth=1,
        ).pack()
        popup.update_idletasks()
        x: int = self._widget.winfo_rootx()
        y: int = self._widget.winfo_rooty() + self._widget.winfo_height()
        if self._anchor is not None:
            x += self._anchor[0]
            y = self._widget.winfo_rooty() + self._anchor[1]
        x = max(0, min(x, popup.winfo_screenwidth() - popup.winfo_reqwidth()))
        y = min(y + POPUP_OFFSET_PIXELS,
                popup.winfo_screenheight() - popup.winfo_reqheight())
        popup.geometry(f"+{x}+{max(0, y)}")
        popup.deiconify()

    def toggle(self) -> None:
        """Toggle click help from a native button's click, Space or Enter.

        Returns:
            None: Keyboard focus stays on the help button.
        """
        if self._popup is None:
            self.show()
        else:
            self.close()

    def close(self) -> None:
        """Cancel a pending hint and destroy its owned popup, if present.

        Returns:
            None: No timer or popup survives concealment or widget destruction.
        """
        if self._timer is not None:
            self._widget.after_cancel(self._timer)
            self._timer = None
        if self._popup is not None:
            popup: tk.Toplevel = self._popup
            self._popup = None
            popup.destroy()

    def _dismiss(self, event: tk.Event) -> None:
        """Close help after Escape, pointer leave or focus departure.

        Args:
            event (tk.Event): Tk dismissal event.

        Returns:
            None: The original event remains available to other handlers.
        """
        self.close()

    def _outside_click(self, event: tk.Event) -> None:
        """Keep help open only for its own button and popup descendants.

        Args:
            event (tk.Event): Main-window button press, before button invocation.

        Returns:
            None: Clicking the help button can still toggle the current popup.
        """
        if event.widget is self._widget:
            return
        if self._popup is not None and str(event.widget).startswith(
            str(self._popup) + "."
        ):
            return
        self.close()

    def _on_unmap(self, event: tk.Event) -> None:
        """Close help when its control or the owning window disappears.

        Args:
            event (tk.Event): Root binding also receives descendant unmaps.

        Returns:
            None: Unrelated widget geometry changes do not dismiss help.
        """
        if event.widget in (self._widget, self._root):
            self.close()

    def _destroy(self, event: tk.Event) -> None:
        """Release root bindings before Tk deletes this control's commands.

        Args:
            event (tk.Event): Destruction notification for the attached widget.

        Returns:
            None: Repeated destruction callbacks have no remaining bindings.
        """
        if event.widget is not self._widget:
            return
        self.close()
        for sequence, identifier in self._bindings:
            self._root.unbind(sequence, identifier)
        self._bindings.clear()


class NotebookHints(ContextHelp):
    """Expose retained translated tab captions for an icon-only notebook."""

    def __init__(self, notebook: ttk.Notebook) -> None:
        """Bind pointer and keyboard-focus hints without changing tab input.

        Args:
            notebook (ttk.Notebook): Icon tabs with translated text metadata.

        Returns:
            None: No hint is shown until a tab is hovered or focused.
        """
        super().__init__(notebook, "", click=True)
        self._notebook: ttk.Notebook = notebook
        self._tab: int | None = None
        notebook.bind("<Motion>", self._motion, add="+")
        notebook.bind("<Leave>", self._dismiss, add="+")
        notebook.bind("<FocusOut>", self._dismiss, add="+")
        notebook.bind("<FocusIn>", self._focus, add="+")
        notebook.bind("<<NotebookTabChanged>>", self._dismiss, add="+")

    def _motion(self, event: tk.Event) -> None:
        """Update a delayed hint only when the pointer enters a different tab.

        Args:
            event (tk.Event): Pointer coordinates relative to the notebook.

        Returns:
            None: The page body and empty tab-strip space have no hint.
        """
        try:
            index: int = self._notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            self._tab = None
            self.close()
            return
        if self._tab != index:
            self._tab = index
            self._anchor = (event.x, round(
                TAB_HINT_HEIGHT_PIXELS * self._notebook.winfo_fpixels("1i")
                / REFERENCE_DPI
            ))
            self._text = str(self._notebook.tab(index, "text"))
            self._schedule(event)

    def _focus(self, event: tk.Event) -> None:
        """Expose the selected caption when keyboard focus enters the tabs.

        Args:
            event (tk.Event): Keyboard-focus arrival on the notebook itself.

        Returns:
            None: Focus inside a page does not show a tab hint.
        """
        if event.widget is self._notebook:
            self._anchor = (0, round(
                TAB_HINT_HEIGHT_PIXELS * self._notebook.winfo_fpixels("1i")
                / REFERENCE_DPI
            ))
            self._text = str(self._notebook.tab("current", "text"))
            self._schedule(event)

    def _dismiss(self, event: tk.Event) -> None:
        """Reset the hovered tab so revisiting it can show its hint again.

        Args:
            event (tk.Event): Hint dismissal event forwarded by Tk.

        Returns:
            None: The next tab hover schedules a fresh hint.
        """
        self._tab = None
        super()._dismiss(event)
