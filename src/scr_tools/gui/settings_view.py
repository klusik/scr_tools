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


class SettingsView(ttk.Frame):
    """Present three small pages while keeping every Tk operation local.

    Attributes:
        notebook (ttk.Notebook): Mouse, screenshot, and general settings pages.
    """

    def __init__(
        self,
        parent: ttk.Frame,
        translator: Translator,
        settings: Settings,
        startup_supported: bool,
    ) -> None:
        """Build and populate the editor on the Tk main thread.

        Args:
            parent (ttk.Frame): Widget that owns this editor.
            translator (Translator): Current locale with English fallback.
            settings (Settings): Applied values used to initialize controls.
            startup_supported (bool): Whether this is an installed executable.

        Returns:
            None: Widgets and variables are initialized in place.
        """
        super().__init__(parent)
        self._translator: Translator = translator
        self._startup_supported: bool = startup_supported
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
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self._build_mouse_page()
        self._build_screenshot_page()
        self._build_general_page()
        self.load(settings)

    def _page(self, title_key: str) -> ttk.Frame:
        """Create a notebook page with consistent two-column sizing.

        Args:
            title_key (str): Catalog key used for its tab caption.

        Returns:
            ttk.Frame: A padded page ready for labels and controls.
        """
        page: ttk.Frame = ttk.Frame(self.notebook, padding=(12, 12))
        page.columnconfigure(1, weight=1)
        self.notebook.add(page, text=self._translator.text(title_key))
        return page

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
        """Create movement and power controls without applying them yet.

        Returns:
            None: The notebook gains one populated page.
        """
        page: ttk.Frame = self._page("tab.mouse")
        self._label(page, 0, "settings.idle")
        ttk.Spinbox(
            page, from_=10, to=86400, textvariable=self._idle, width=12
        ).grid(row=0, column=1, sticky="w", pady=5)
        self._label(page, 1, "settings.pattern")
        ttk.Combobox(
            page,
            textvariable=self._pattern,
            values=tuple(self._patterns.values()),
            state="readonly",
            width=20,
        ).grid(row=1, column=1, sticky="w", pady=5)
        self._label(page, 2, "settings.distance")
        ttk.Spinbox(
            page, from_=1, to=1000, textvariable=self._distance, width=12
        ).grid(row=2, column=1, sticky="w", pady=5)
        self._label(page, 3, "settings.duration")
        ttk.Spinbox(
            page,
            from_=0.2,
            to=10.0,
            increment=0.1,
            textvariable=self._duration,
            width=12,
        ).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Separator(page).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=9
        )
        ttk.Checkbutton(
            page,
            text=self._translator.text("settings.prevent_sleep"),
            variable=self._prevent_sleep,
            command=self._update_display_control,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        self._display_control: ttk.Checkbutton = ttk.Checkbutton(
            page,
            text=self._translator.text("settings.display_awake"),
            variable=self._display_awake,
        )
        self._display_control.grid(
            row=6, column=0, columnspan=2, sticky="w", pady=4, padx=(20, 0)
        )
        ttk.Label(
            page,
            text=self._translator.text("settings.movement_hint"),
            style="Secondary.TLabel",
            wraplength=475,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _build_screenshot_page(self) -> None:
        """Create noninteractive capture preferences and a folder picker.

        Returns:
            None: The notebook gains its screenshot page.
        """
        page: ttk.Frame = self._page("tab.screenshots")
        self._label(page, 0, "settings.hotkey")
        ttk.Entry(page, textvariable=self._hotkey, width=27).grid(
            row=0, column=1, sticky="ew", pady=5
        )
        ttk.Label(
            page,
            text=self._translator.text("settings.hotkey_hint"),
            style="Secondary.TLabel",
            wraplength=450,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 9))
        self._label(page, 2, "settings.capture_mode")
        ttk.Combobox(
            page,
            textvariable=self._mode,
            values=tuple(self._modes.values()),
            state="readonly",
            width=30,
        ).grid(row=2, column=1, sticky="ew", pady=5)
        self._label(page, 3, "settings.folder")
        folder_row: ttk.Frame = ttk.Frame(page)
        folder_row.columnconfigure(0, weight=1)
        folder_row.grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Entry(folder_row, textvariable=self._folder).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(
            folder_row,
            text=self._translator.text("button.browse"),
            command=self._browse_folder,
        ).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(
            page,
            text=self._translator.text("settings.screenshot_hint"),
            style="Secondary.TLabel",
            wraplength=475,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _build_general_page(self) -> None:
        """Create launch preferences and explain source-mode startup.

        Returns:
            None: The notebook gains its general page.
        """
        page: ttk.Frame = self._page("tab.general")
        ttk.Checkbutton(
            page,
            text=self._translator.text("settings.minimized"),
            variable=self._minimized,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
        startup: ttk.Checkbutton = ttk.Checkbutton(
            page,
            text=self._translator.text("settings.startup"),
            variable=self._startup,
        )
        startup.grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        if not self._startup_supported:
            startup.state(["disabled"])
        ttk.Label(
            page,
            text=self._translator.text(
                "settings.startup_supported"
                if self._startup_supported
                else "settings.startup_source"
            ),
            style="Secondary.TLabel",
            wraplength=475,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
        self._label(page, 3, "settings.language")
        ttk.Combobox(
            page,
            textvariable=self._language,
            values=tuple(self._languages.values()),
            state="readonly",
            width=22,
        ).grid(row=3, column=1, sticky="w", pady=5)
        ttk.Separator(page).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=9
        )
        ttk.Label(
            page,
            text=self._translator.text("settings.tray_hint"),
            style="Secondary.TLabel",
            wraplength=475,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(5, 8))
        ttk.Label(
            page,
            text=self._translator.text("settings.privacy_hint"),
            style="Secondary.TLabel",
            wraplength=475,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=5)

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
