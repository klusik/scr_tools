# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/gui/main_window.py
# Module Type: Main application window
# Purpose: Present status and explicit user actions without worker-thread UI.
# Responsibilities: Build a compact ttk window and route close/minimize to tray.
# Author: Rudolf Klusal
# License: MIT

"""Main-thread presentation; the tray owns the only normal Exit command."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import font, ttk

from scr_tools.configuration import Settings
from scr_tools.gui.settings_view import SettingsView
from scr_tools.localization.translator import Translator
from scr_tools.version import VERSION


MOVEMENT_REVEAL_SEQUENCES: tuple[str, ...] = (
    "<Control-Shift-KeyPress-S>", "<Control-Shift-KeyPress-s>",
)
MINIMUM_WINDOW_WIDTH: int = 590


@dataclass(frozen=True, slots=True)
class WindowActions:
    """Callbacks implemented by the application on the Tk main thread.

    Attributes:
        apply (Callable[[], None]): Validate and persist the edited settings.
        toggle (Callable[[bool], None]): Immediately enable or pause movement.
        test (Callable[[], None]): Request one explicit, cancellable cycle.
        capture (Callable[[], None]): Enqueue an explicit screenshot request.
        open_folder (Callable[[], None]): Open the applied screenshot folder.
        hide (Callable[[], None]): Hide only if a working tray remains available.
    """

    apply: Callable[[], None]
    toggle: Callable[[bool], None]
    test: Callable[[], None]
    capture: Callable[[], None]
    open_folder: Callable[[], None]
    hide: Callable[[], None]


class MainWindow:
    """Screenshot controls with movement details revealed only on request."""

    def __init__(
        self,
        root: tk.Tk,
        translator: Translator,
        settings: Settings,
        actions: WindowActions,
        icon_path: Path,
        startup_supported: bool,
    ) -> None:
        """Build the application view without starting or stopping services.

        Args:
            root (tk.Tk): Tk root owned by the application main thread.
            translator (Translator): Translation lookup for every caption.
            settings (Settings): Initial validated preferences.
            actions (WindowActions): Main-thread command handlers.
            icon_path (Path): Maintained multi-resolution Windows icon.
            startup_supported (bool): Whether installed auto-start is available.

        Returns:
            None: The window and its controls are ready for display.
        """
        self.root: tk.Tk = root
        self._translator: Translator = translator
        self._actions: WindowActions = actions
        self._enabled: tk.BooleanVar = tk.BooleanVar(
            root, value=settings.mover_enabled
        )
        self._status: tk.StringVar = tk.StringVar(
            root, value=translator.text("status.starting")
        )
        self._detail: tk.StringVar = tk.StringVar(root)
        self._last_movement: tk.StringVar = tk.StringVar(
            root, value=translator.text("status.last_never")
        )
        self._capture_status: tk.StringVar = tk.StringVar(
            root, value=translator.text("capture.ready")
        )
        self._notice: tk.StringVar = tk.StringVar(
            root, value=translator.text("settings.ready")
        )
        self._movement_notice: tk.StringVar = tk.StringVar(root)
        self._status_cache: tuple[str, str, bool] | None = None
        self._build_style()
        root.title(translator.text("app.title"))
        root.protocol("WM_DELETE_WINDOW", self._request_hide)
        root.bind("<Unmap>", self._on_unmap, add="+")
        # A window-local binding reveals existing controls on the Tk thread.
        # It neither installs a global hotkey nor changes movement settings.
        for sequence in MOVEMENT_REVEAL_SEQUENCES:
            root.bind(sequence, self._reveal_movement_settings, add="+")
        if icon_path.is_file():
            root.iconbitmap(default=str(icon_path))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        body: ttk.Frame = ttk.Frame(root, padding=(16, 12))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)
        header: ttk.Frame = ttk.Frame(body)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text=translator.text("app.title"), style="Title.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header, text=VERSION, style="Secondary.TLabel"
        ).grid(row=0, column=1, sticky="e")
        status_row: ttk.Frame = ttk.Frame(body)
        status_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        status_row.columnconfigure(0, weight=1)
        ttk.Label(
            status_row, textvariable=self._status, style="Status.TLabel"
        ).grid(row=0, column=0, sticky="w")
        self._toggle: ttk.Checkbutton = ttk.Checkbutton(
            status_row,
            text=translator.text("button.mover_enabled"),
            variable=self._enabled,
            command=self._toggle_mover,
        )
        self._toggle.grid(row=0, column=1, sticky="e", padx=(12, 0))
        detail_label: ttk.Label = ttk.Label(
            body, textvariable=self._detail, style="Secondary.TLabel",
            wraplength=510,
        )
        detail_label.grid(row=2, column=0, sticky="w", pady=(3, 10))
        self.settings_view: SettingsView = SettingsView(
            body, translator, settings, startup_supported
        )
        self.settings_view.grid(row=3, column=0, sticky="nsew")
        actions_row: ttk.Frame = ttk.Frame(body)
        actions_row.grid(row=4, column=0, sticky="ew", pady=(12, 6))
        actions_row.columnconfigure(2, weight=1)
        self._test: ttk.Button = ttk.Button(
            actions_row,
            text=translator.text("button.test"),
            command=actions.test,
        )
        self._test.grid(row=0, column=0, sticky="w")
        self._capture: ttk.Button = ttk.Button(
            actions_row,
            text=translator.text("button.capture"),
            command=actions.capture,
        )
        self._capture.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._apply: ttk.Button = ttk.Button(
            actions_row,
            text=translator.text("button.apply"),
            command=actions.apply,
        )
        self._apply.grid(row=0, column=3, sticky="e")
        last_movement_label: ttk.Label = ttk.Label(
            body,
            textvariable=self._last_movement,
            style="Secondary.TLabel",
        )
        last_movement_label.grid(row=5, column=0, sticky="w", pady=(2, 2))
        capture_row: ttk.Frame = ttk.Frame(body)
        capture_row.grid(row=6, column=0, sticky="ew", pady=2)
        capture_row.columnconfigure(0, weight=1)
        self._capture_label: ttk.Label = ttk.Label(
            capture_row,
            textvariable=self._capture_status,
            style="Secondary.TLabel",
            wraplength=390,
        )
        self._capture_label.grid(row=0, column=0, sticky="w")
        self._folder_button: ttk.Button = ttk.Button(
            capture_row,
            text=translator.text("button.open_folder"),
            command=actions.open_folder,
        )
        self._folder_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Separator(body).grid(row=7, column=0, sticky="ew", pady=(8, 7))
        self._notice_label: ttk.Label = ttk.Label(
            body, textvariable=self._notice, wraplength=510
        )
        self._notice_label.grid(row=8, column=0, sticky="ew")
        self._movement_notice_label: ttk.Label = ttk.Label(
            body, textvariable=self._movement_notice, wraplength=510
        )
        self._movement_notice_label.grid(row=9, column=0, sticky="ew")
        self._movement_widgets: tuple[tk.Widget, ...] = (
            status_row, detail_label, self._test, last_movement_label,
            self._movement_notice_label,
        )
        self._set_movement_visible(False)
        # Geometry is derived from Tk's DPI-scaled font and widget requests.
        # No hard-coded physical window height clips controls at 150/200% DPI.
        root.update_idletasks()
        width: int = max(root.winfo_reqwidth(), MINIMUM_WINDOW_WIDTH)
        height: int = root.winfo_reqheight()
        root.minsize(width, height)
        root.geometry(f"{width}x{height}")

    def _set_movement_visible(self, visible: bool) -> None:
        """Change presentation only, preserving settings and running services.

        Args:
            visible (bool): Whether movement controls and status are exposed.

        Returns:
            None: Existing widget values survive concealment and restoration.
        """
        self.settings_view.set_movement_visible(visible)
        for widget in self._movement_widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()
        self.root.after_idle(self._fit_content)

    def _reveal_movement_settings(self, event: tk.Event) -> str:
        """Expose the mouse page for this visible window session.

        Args:
            event (tk.Event): Window-local Ctrl+Shift+S key press.

        Returns:
            str: Tk's break sentinel consumes the shortcut without editing text.
        """
        if self.root.state() in ("normal", "zoomed"):
            self._set_movement_visible(True)
        return "break"

    def _build_style(self) -> None:
        """Use Windows ttk rendering and point-sized scalable Segoe UI fonts.

        Returns:
            None: Theme and the few application-specific styles are installed.
        """
        style: ttk.Style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name, root=self.root).configure(
                family="Segoe UI", size=10
            )
        style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Secondary.TLabel", foreground="#515b68")
        style.configure("TButton", padding=(9, 4))
        style.configure("TNotebook.Tab", padding=(12, 5))

    def _request_hide(self) -> None:
        """Route X and Alt+F4 to the application tray-availability guard.

        Returns:
            None: This method never destroys Tk or requests ordinary shutdown.
        """
        self._set_movement_visible(False)
        self._actions.hide()

    def _on_unmap(self, event: tk.Event) -> None:
        """Convert a real minimize operation into the same tray lifecycle.

        Args:
            event (tk.Event): Tk unmap event, possibly from a child widget.

        Returns:
            None: Child unmaps are ignored; root withdrawal conceals controls
                without recursively invoking the tray hide handler.
        """
        if event.widget is self.root:
            state: str = self.root.state()
            if state in ("iconic", "withdrawn"):
                self._set_movement_visible(False)
            if state == "iconic":
                self._actions.hide()

    def _toggle_mover(self) -> None:
        """Pass the enabled checkbox value to the immediate-action handler.

        Returns:
            None: Persistence and failure rollback belong to the application.
        """
        self._actions.toggle(self._enabled.get())

    def show(self) -> None:
        """Restore and focus the existing window, including second launches.

        Returns:
            None: The single existing root becomes visible.
        """
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.after_idle(self._fit_content)

    def hide(self) -> None:
        """Withdraw the window after the application confirms a live tray.

        Returns:
            None: Background services and the root event loop remain alive.
        """
        self._set_movement_visible(False)
        self.root.withdraw()

    def set_status(self, title: str, detail: str, enabled: bool) -> None:
        """Update the header only when the displayed values actually change.

        Args:
            title (str): Already translated primary status.
            detail (str): Already translated countdown or pause explanation.
            enabled (bool): Applied enabled preference, not worker readiness.

        Returns:
            None: Redundant StringVar writes are skipped.
        """
        current: tuple[str, str, bool] = (title, detail, enabled)
        if current != self._status_cache:
            self._status.set(title)
            self._detail.set(detail)
            self._enabled.set(enabled)
            self._status_cache = current

    def set_notice(self, message: str, error: bool = False) -> None:
        """Display an unobtrusive setting or operational result.

        Args:
            message (str): Translated message, without sensitive diagnostics.
            error (bool): Whether the message should use an error foreground.

        Returns:
            None: Existing status is replaced without a modal dialog.
        """
        self._notice.set(message)
        self._notice_label.configure(
            foreground="#a12424" if error else "#24364b"
        )
        self.root.after_idle(self._fit_content)

    def set_capture_status(self, message: str) -> None:
        """Display the most recent capture result or queued-state message.

        Args:
            message (str): Translated text; a basename is preferred to a path.

        Returns:
            None: Capture never opens a file-selection or confirmation dialog.
        """
        self._capture_status.set(message)
        self.root.after_idle(self._fit_content)

    def set_movement_notice(self, message: str, error: bool = False) -> None:
        """Retain movement results within the optionally visible controls.

        Args:
            message (str): Translated movement, input, or power diagnostic.
            error (bool): Whether the result should use an error foreground.

        Returns:
            None: Hidden results cannot replace ordinary application notices.
        """
        self._movement_notice.set(message)
        self._movement_notice_label.configure(
            foreground="#a12424" if error else "#24364b"
        )
        self.root.after_idle(self._fit_content)

    def _fit_content(self) -> None:
        """Grow the visible window if wrapped status text needs more room.

        Returns:
            None: Existing larger user geometry is preserved. Hidden windows
            keep their geometry until restored, when Tk recomputes requests.
        """
        if self.root.state() == "withdrawn":
            return
        self.root.update_idletasks()
        self.root.minsize(
            max(self.root.winfo_reqwidth(), MINIMUM_WINDOW_WIDTH),
            self.root.winfo_reqheight(),
        )
        width: int = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        height: int = max(self.root.winfo_height(), self.root.winfo_reqheight())
        if (width, height) != (
            self.root.winfo_width(), self.root.winfo_height()
        ):
            self.root.geometry(f"{width}x{height}")

    def set_last_movement(self, message: str) -> None:
        """Show when the most recent uninterrupted movement completed.

        Args:
            message (str): Translated local time or the initial never-run text.

        Returns:
            None: The movement detail label is updated.
        """
        self._last_movement.set(message)

    def set_stopping(self) -> None:
        """Disable explicit actions while workers finish deterministic cleanup.

        Returns:
            None: Tk stays responsive until the application destroys it.
        """
        for widget in (
            self._toggle, self._test, self._capture,
            self._apply, self._folder_button,
        ):
            widget.state(["disabled"])
        self.set_notice(self._translator.text("status.stopping"))
