# Project: SCR Tools
# Repository: SCR-Tools (local source repository)
# File path: src/scr_tools/gui/settings_view.py
# Module Type: Settings editor
# Purpose: Edit validated application settings in a compact native interface.
# Responsibilities: Own Tk variables, collect typed values, and browse folders.
# Author: Rudolf Klusal
# License: MIT

"""Settings widgets without access to native workers or persistence."""

from dataclasses import replace
from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

from scr_tools.configuration import (
    ConfigurationError,
    MovementPattern,
    Settings,
    ScreenshotMode,
    validate_settings,
)
from scr_tools.localization.translator import Translator
from scr_tools.gui.compact_style import CompactStyle, IconName, PANEL_RADIUS
from scr_tools.gui.context_help import ContextHelp, NotebookHints


class SettingsView(ttk.Frame):
    """Present three small pages while keeping every Tk operation local.

    Attributes:
        notebook (ttk.Notebook): Screenshot, general, and additional pages.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        translator: Translator,
        settings: Settings,
        startup_supported: bool,
        presentation: CompactStyle,
    ) -> None:
        """Build and populate the editor on the Tk main thread.

        Args:
            parent (ttk.Frame): Widget that owns this editor.
            translator (Translator): Current locale with English fallback.
            settings (Settings): Applied values used to initialize controls.
            startup_supported (bool): Whether this is an installed executable.
            presentation (CompactStyle): Root-owned images and control styles.

        Returns:
            None: Widgets and variables are initialized in place.
        """
        super().__init__(parent)
        self._translator: Translator = translator
        self._startup_supported: bool = startup_supported
        self._presentation: CompactStyle = presentation
        self._help: list[ContextHelp] = []
        self._page_help: dict[str, ContextHelp] = {}
        # Place the rounded decoration independently of grid geometry. Keeping
        # it behind the native notebook avoids image-element geometry cycles
        # in Tcl/Tk 9 while preserving native tab focus and hit testing.
        self._surface: tk.Canvas = tk.Canvas(
            self, background=presentation.background,
            borderwidth=0, highlightthickness=0, takefocus=False,
        )
        self._surface.place(x=0, y=0, relwidth=1, relheight=1)
        self._surface_shape: int = self._surface.create_polygon(
            (0, 0, 1, 0, 1, 1, 0, 1), fill=presentation.panel,
            outline="", smooth=True,
        )
        self.bind("<Configure>", self._paint_surface, add="+")
        self._idle: tk.StringVar = tk.StringVar(self)
        self._pattern: tk.StringVar = tk.StringVar(self)
        self._distance: tk.StringVar = tk.StringVar(self)
        self._duration: tk.StringVar = tk.StringVar(self)
        self._prevent_sleep: tk.BooleanVar = tk.BooleanVar(self)
        self._display_awake: tk.BooleanVar = tk.BooleanVar(self)
        self._hotkey: tk.StringVar = tk.StringVar(self)
        self._mode: tk.StringVar = tk.StringVar(self)
        self._folder: tk.StringVar = tk.StringVar(self)
        self._minimized: tk.BooleanVar = tk.BooleanVar(self)
        self._startup: tk.BooleanVar = tk.BooleanVar(self)
        self._language: tk.StringVar = tk.StringVar(self)
        self._languages: dict[str, str] = translator.available_languages()
        if settings.language not in self._languages:
            self._languages[settings.language] = settings.language
        self._patterns: dict[MovementPattern, str] = {
            "rectangle": translator.text("settings.rectangle"),
            "circle": translator.text("settings.circle"),
        }
        self._modes: dict[ScreenshotMode, str] = {
            "all": translator.text("settings.mode_all"),
            "current": translator.text("settings.mode_current"),
            "each": translator.text("settings.mode_each"),
        }
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.notebook: ttk.Notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self._help.append(NotebookHints(self.notebook))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")
        self._build_mouse_page()
        self._build_screenshot_page()
        self._build_general_page()
        self.set_movement_visible(False)
        self.load(settings)

    def _paint_surface(self, event: tk.Event) -> None:
        """Resize the quietly rounded backdrop without requesting layout.

        Args:
            event (tk.Event): Editor size in current physical pixels.

        Returns:
            None: Native content stays inset from the decorative curved edge.
        """
        width: int = event.width
        height: int = event.height
        radius: int = min(self._presentation.pixels(PANEL_RADIUS),
                          width // 2, height // 2)
        self._surface.coords(
            self._surface_shape,
            radius, 0, width - radius, 0, width, 0, width, radius,
            width, height - radius, width, height, width - radius, height,
            radius, height, 0, height, 0, height - radius, 0, radius, 0, 0,
        )

    def _on_tab_changed(self, event: tk.Event) -> None:
        """Notify the window after native notebook selection changes.

        Args:
            event (tk.Event): Notebook page-selection notification.

        Returns:
            None: The window fits native requests on its next idle callback.
        """
        self.event_generate("<<SettingsLayoutChanged>>")

    def set_movement_visible(self, visible: bool) -> None:
        """Reveal or conceal additional settings without changing form values.

        Args:
            visible (bool): Whether to expose and select the additional page.

        Returns:
            None: Concealment selects Screenshots if that page was active.
                Hidden controls retain both applied and pending edits.
        """
        if visible:
            if str(self._mouse_page) not in self.notebook.tabs():
                self.notebook.insert(
                    0, self._mouse_page,
                    text=self._translator.text("tab.mouse"),
                    image=self._presentation.control_images("settings"), compound="image",
                )
            self.notebook.select(self._mouse_page)
        else:
            for help_popup in self._help:
                help_popup.close()
            if self.notebook.select() == str(self._mouse_page):
                self.notebook.select(self._screenshot_page)
            if str(self._mouse_page) in self.notebook.tabs():
                # Forget removes the page from notebook size requests, unlike
                # hide. The existing frame and all its variables stay alive.
                self.notebook.forget(self._mouse_page)
        self.event_generate("<<SettingsLayoutChanged>>")

    def _page(self, title_key: str, icon: IconName) -> ttk.Frame:
        """Create a notebook page with consistent two-column sizing.

        Args:
            title_key (str): Catalog key used for its tab caption.
            icon (IconName): Semantic line icon shown in the compact tab strip.

        Returns:
            ttk.Frame: A padded page ready for labels and controls.
        """
        page: ttk.Frame = ttk.Frame(
            self.notebook, padding=(10, 8), style="Panel.TFrame"
        )
        page.columnconfigure(1, weight=1)
        self.notebook.add(
            page, text=self._translator.text(title_key),
            image=self._presentation.control_images(icon), compound="image",
        )
        return page

    def _heading(self, page: ttk.Frame, title_key: str,
                 help_keys: tuple[str, ...]) -> None:
        """Place a concise page title and keyboard-accessible context help.

        Args:
            page (ttk.Frame): Destination page with two field columns.
            title_key (str): Translated page-heading key.
            help_keys (tuple[str, ...]): Ordered translated help paragraphs.

        Returns:
            None: Long guidance is available without occupying the form.
        """
        header: ttk.Frame = ttk.Frame(page, style="Panel.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text=self._translator.text(title_key), style="PageTitle.TLabel"
        ).grid(row=0, column=0, sticky="w")
        button: ttk.Button = ttk.Button(
            header, text=self._translator.text("button.help_symbol"),
            image=self._presentation.control_images("help"), compound="image",
            style="Help.TButton",
        )
        button.grid(row=0, column=1, sticky="e")
        help_popup: ContextHelp = ContextHelp(
            button, "\n\n".join(self._translator.text(key) for key in help_keys),
            click=True,
        )
        self._help.append(help_popup)
        self._page_help[title_key] = help_popup
        button.configure(command=help_popup.toggle)
        button.bind("<Return>", lambda event: help_popup.toggle())

    def _switch(self, page: ttk.Frame, row: int, key: str,
                variable: tk.BooleanVar,
                command: Callable[[], None] | None = None) -> ttk.Checkbutton:
        """Align a binary preference with a native keyboard-operated switch.

        Args:
            page (ttk.Frame): Destination settings page.
            row (int): Zero-based grid row.
            key (str): Translated field caption and native control label.
            variable (tk.BooleanVar): Existing preference variable.
            command (Callable[[], None] | None): Optional dependency refresh.

        Returns:
            ttk.Checkbutton: Native checkbutton with a switch indicator.
        """
        self._label(page, row, key)
        control: ttk.Checkbutton = ttk.Checkbutton(
            page, text=self._translator.text(key), variable=variable,
            command=command, style="Indicator.Switch.TCheckbutton",
        )
        control.grid(row=row, column=1, sticky="e", pady=4)
        return control

    def _label(self, page: ttk.Frame, row: int, key: str) -> None:
        """Place a translated field label in the page's first column.

        Args:
            page (ttk.Frame): Destination page.
            row (int): Zero-based grid row.
            key (str): Translation catalog key.

        Returns:
            None: The new label is owned by the page.
        """
        ttk.Label(page, text=self._translator.text(key)).grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=5
        )

    def _build_mouse_page(self) -> None:
        """Create additional controls without applying their values yet.

        Returns:
            None: The notebook gains one populated page.
        """
        self._mouse_page: ttk.Frame = self._page("tab.mouse", "settings")
        page: ttk.Frame = self._mouse_page
        self._heading(page, "tab.mouse", ("settings.movement_hint",))
        self._label(page, 1, "settings.idle")
        ttk.Spinbox(
            page, from_=10, to=86400, textvariable=self._idle, width=9
        ).grid(row=1, column=1, sticky="e", pady=5)
        self._label(page, 2, "settings.pattern")
        patterns: ttk.Frame = ttk.Frame(page, style="Panel.TFrame")
        patterns.grid(row=2, column=1, sticky="e", pady=5)
        for column, pattern in enumerate(self._patterns):
            button: ttk.Radiobutton = ttk.Radiobutton(
                patterns, text=self._patterns[pattern],
                image=self._presentation.control_images(pattern), compound="image",
                variable=self._pattern, value=self._patterns[pattern],
                style="Mode.TRadiobutton",
            )
            button.grid(row=0, column=column, padx=(4, 0))
            self._help.append(ContextHelp(button, self._patterns[pattern]))
        self._label(page, 3, "settings.distance")
        ttk.Spinbox(
            page, from_=1, to=1000, textvariable=self._distance, width=9
        ).grid(row=3, column=1, sticky="e", pady=5)
        self._label(page, 4, "settings.duration")
        ttk.Spinbox(
            page,
            from_=0.2,
            to=10.0,
            increment=0.1,
            textvariable=self._duration,
            width=9,
        ).grid(row=4, column=1, sticky="e", pady=5)
        ttk.Separator(page).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=9
        )
        self._sleep_control: ttk.Checkbutton = self._switch(
            page, 6, "settings.prevent_sleep", self._prevent_sleep,
            self._update_display_control,
        )
        self._display_control: ttk.Checkbutton = self._switch(
            page, 7, "settings.display_awake", self._display_awake
        )

    def _build_screenshot_page(self) -> None:
        """Create noninteractive capture preferences and a folder picker.

        Returns:
            None: The notebook gains its screenshot page.
        """
        self._screenshot_page: ttk.Frame = self._page("tab.screenshots", "camera")
        page: ttk.Frame = self._screenshot_page
        self._heading(page, "tab.screenshots", (
            "settings.hotkey_hint", "settings.screenshot_hint",
        ))
        ttk.Label(
            page, text=self._translator.text("settings.hotkey"),
            image=self._presentation.icon("keyboard"), compound="left",
        ).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Entry(page, textvariable=self._hotkey, width=24).grid(
            row=1, column=1, sticky="e", pady=8
        )
        ttk.Label(
            page, text=self._translator.text("settings.capture_mode"),
            image=self._presentation.icon("current"), compound="left",
        ).grid(row=2, column=0, sticky="w", padx=(0, 12), pady=8)
        modes: ttk.Frame = ttk.Frame(page, style="Panel.TFrame")
        modes.grid(row=2, column=1, sticky="e", pady=8)
        self._mode_controls: dict[ScreenshotMode, ttk.Radiobutton] = {}
        for column, mode in enumerate(self._modes):
            control: ttk.Radiobutton = ttk.Radiobutton(
                modes, text=self._modes[mode],
                image=self._presentation.control_images(mode), compound="image",
                variable=self._mode, value=self._modes[mode],
                style="Mode.TRadiobutton",
            )
            control.grid(row=0, column=column, padx=(4, 0))
            self._mode_controls[mode] = control
            self._help.append(ContextHelp(control, self._modes[mode]))
        folder_row: ttk.Frame = ttk.Frame(page, style="Panel.TFrame")
        folder_row.columnconfigure(1, weight=1)
        folder_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        label: ttk.Label = ttk.Label(
            folder_row, text=self._translator.text("settings.folder"),
            image=self._presentation.icon("folder"), compound="image",
        )
        label.grid(row=0, column=0, padx=(0, 8))
        self._help.append(ContextHelp(label, self._translator.text("settings.folder")))
        self._folder_control: ttk.Entry = ttk.Entry(
            folder_row, textvariable=self._folder, width=1
        )
        self._folder_control.grid(
            row=0, column=1, sticky="ew"
        )
        browse: ttk.Button = ttk.Button(
            folder_row,
            text=self._translator.text("button.browse"),
            command=self._browse_folder,
            image=self._presentation.control_images("browse"), compound="image",
            style="Panel.Icon.TButton",
        )
        browse.grid(row=0, column=2, padx=(6, 0))
        self._help.append(ContextHelp(browse, self._translator.text("button.browse")))

    def _build_general_page(self) -> None:
        """Create launch preferences and explain source-mode startup.

        Returns:
            None: The notebook gains its general page.
        """
        page: ttk.Frame = self._page("tab.general", "settings")
        self._heading(page, "tab.general", (
            "settings.startup_supported" if self._startup_supported
            else "settings.startup_source",
            "settings.tray_hint", "settings.privacy_hint", "settings.ready",
        ))
        self._startup_control: ttk.Checkbutton = self._switch(
            page, 1, "settings.startup", self._startup
        )
        if not self._startup_supported:
            self._startup_control.state(["disabled"])
        self._minimized_control: ttk.Checkbutton = self._switch(
            page, 2, "settings.minimized", self._minimized
        )
        self._label(page, 3, "settings.language")
        ttk.Combobox(
            page,
            textvariable=self._language,
            values=tuple(self._languages.values()),
            state="readonly",
            width=24,
        ).grid(row=3, column=1, sticky="e", pady=5)

    def _update_display_control(self) -> None:
        """Reflect that display requests require system-sleep prevention.

        Returns:
            None: Only the dependent control's enabled state changes.
        """
        self._display_control.state(
            ["!disabled"] if self._prevent_sleep.get() else ["disabled"]
        )

    def _browse_folder(self) -> None:
        """Let an explicit Settings action select a screenshot directory.

        Returns:
            None: Cancel leaves the existing value untouched.
        """
        current: Path = Path(self._folder.get()).expanduser()
        selected: str = filedialog.askdirectory(
            parent=self,
            title=self._translator.text("settings.choose_folder"),
            initialdir=str(current if current.is_dir() else Path.home()),
            mustexist=False,
        )
        if selected:
            self._folder.set(selected)
            self._folder_control.xview_moveto(1)

    def load(self, settings: Settings) -> None:
        """Replace editor values with successfully applied settings.

        Args:
            settings (Settings): Validated settings from the application.

        Returns:
            None: Form values and dependent control states are refreshed.
        """
        self._idle.set(str(settings.idle_seconds))
        self._pattern.set(self._patterns[settings.pattern])
        self._distance.set(str(settings.distance_pixels))
        self._duration.set(f"{settings.duration_seconds:g}")
        self._prevent_sleep.set(settings.prevent_sleep)
        self._display_awake.set(settings.keep_displays_awake)
        self._hotkey.set(settings.screenshot_hotkey)
        self._mode.set(self._modes[settings.screenshot_mode])
        self._folder.set(settings.screenshot_folder)
        # Keep the useful destination suffix visible when the absolute path
        # exceeds the field, while retaining normal full-path editing.
        self._folder_control.xview_moveto(1)
        self._minimized.set(settings.start_minimized)
        self._startup.set(settings.start_with_windows)
        self._language.set(self._languages.get(
            settings.language, settings.language
        ))
        self._update_display_control()

    def set_hotkey(self, hotkey: str) -> None:
        """Restore only the shortcut field after a failed asynchronous rebind.

        Args:
            hotkey (str): Previously configured shortcut to show in the form.

        Returns:
            None: Other unsaved settings are preserved.
        """
        self._hotkey.set(hotkey)

    def collect(self, current: Settings) -> Settings:
        """Parse every edited field and validate its domain constraints.

        Args:
            current (Settings): Applied settings supplying noneditable fields.

        Returns:
            Settings: A new validated object, without writing or applying it.

        Raises:
            ConfigurationError: A number, folder, shortcut, or bound is invalid.
        """
        try:
            idle_seconds: int = int(self._idle.get().strip())
            distance_pixels: int = int(self._distance.get().strip())
            duration_seconds: float = float(self._duration.get().strip())
        except ValueError as error:
            raise ConfigurationError("settings.invalid_number") from error
        pattern: MovementPattern | None = next(
            (key for key, label in self._patterns.items()
             if label == self._pattern.get()),
            None,
        )
        if pattern is None:
            raise ConfigurationError("configuration.pattern_invalid")
        mode: ScreenshotMode | None = next(
            (key for key, label in self._modes.items()
             if label == self._mode.get()),
            None,
        )
        if mode is None:
            raise ConfigurationError("configuration.mode_invalid")
        language: str | None = next(
            (key for key, label in self._languages.items()
             if label == self._language.get()),
            None,
        )
        if language is None:
            raise ConfigurationError("configuration.language_invalid")
        candidate: Settings = replace(
            current,
            idle_seconds=idle_seconds,
            pattern=pattern,
            distance_pixels=distance_pixels,
            duration_seconds=duration_seconds,
            prevent_sleep=self._prevent_sleep.get(),
            keep_displays_awake=self._display_awake.get(),
            screenshot_hotkey=self._hotkey.get().strip(),
            screenshot_mode=mode,
            screenshot_folder=self._folder.get().strip(),
            start_minimized=self._minimized.get(),
            start_with_windows=(
                self._startup.get()
                if self._startup_supported
                else current.start_with_windows
            ),
            language=language,
        )
        return validate_settings(candidate)
