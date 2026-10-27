# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: src/scr_tools/gui/compact_style.py
# Module Type: Main-thread presentation resources
# Purpose: Provide compact ttk styles and DPI-scaled control imagery.
# Responsibilities: Own icon images, switch indicators and system-color styles.
# Author: Rudolf Klusal
# License: MIT

"""Small local line icons and native checkbutton switch presentation."""

import math
import tkinter as tk
from tkinter import font, ttk
from typing import Literal

from PIL import Image, ImageDraw, ImageTk


type IconName = Literal[
    "camera", "settings", "mouse", "all", "current", "each",
    "folder", "browse", "help", "check", "play", "keyboard",
    "rectangle", "circle",
]
type ControlState = Literal[
    "normal", "hover", "selected", "focus", "selected_focus", "disabled",
]
type StyleNode = tuple[str, dict[str, str | list[StyleNode]]]
type IconPath = tuple[tuple[float, float], ...]
ICON_PATHS: dict[IconName, tuple[IconPath, ...]] = {
    "camera": (((2, 4), (5, 4), (6, 2), (10, 2), (11, 4), (14, 4),
                (14, 13), (2, 13), (2, 4)),),
    "settings": (((2, 4), (14, 4)), ((2, 8), (14, 8)),
                 ((2, 12), (14, 12)), ((5, 2), (5, 6)),
                 ((11, 6), (11, 10)), ((6, 10), (6, 14))),
    "mouse": (((3, 2), (13, 8), (8, 9), (6, 14), (3, 2)),),
    "all": (((1, 3), (11, 3), (11, 11), (1, 11), (1, 3)),
            ((5, 5), (15, 5), (15, 13), (5, 13), (5, 5))),
    "current": (((2, 2), (14, 2), (14, 11), (2, 11), (2, 2)),
                ((8, 11), (8, 14)), ((5, 14), (11, 14))),
    "each": (((1, 4), (1, 12)), ((4, 3), (4, 13)),
             ((7, 2), (14, 2), (14, 14), (7, 14), (7, 2))),
    "folder": (((1, 4), (1, 2), (6, 2), (8, 4), (14, 4),
                (14, 6)), ((1, 6), (15, 6), (12, 13), (1, 13), (1, 6))),
    "browse": (((4, 8), (4, 8.4)), ((8, 8), (8, 8.4)),
               ((12, 8), (12, 8.4))),
    "help": (((5, 5), (5, 4), (6, 2), (10, 2), (12, 4),
              (12, 6), (8, 9), (8, 10)), ((8, 13), (8, 13.5))),
    "check": (((3, 8), (6, 11), (13, 4)),),
    "play": (((5, 3), (12, 8), (5, 13), (5, 3)),),
    "keyboard": (((1, 3), (15, 3), (15, 13), (1, 13), (1, 3)),
                 ((4, 6), (4, 7)), ((7, 6), (7, 7)),
                 ((10, 6), (10, 7)), ((4, 10), (12, 10))),
    "rectangle": (((2, 4), (14, 4), (14, 12), (2, 12), (2, 4)),),
    "circle": (),
}
ICON_CIRCLES: dict[IconName, tuple[float, float, float, float]] = {
    "camera": (5, 5, 11, 11), "circle": (2, 2, 14, 14),
}
ICON_SIZE: int = 16
IMAGE_SUPERSAMPLING: int = 4
SWITCH_WIDTH: int = 28
SWITCH_HEIGHT: int = 16
PANEL_RADIUS: int = 7
REFERENCE_DPI: int = 96
PANEL_LIFT: float = 0.65
SELECTED_TINT: float = 0.10
FIELD_LINE_TINT: float = 0.12
SWITCH_ACTIVE_TINT: float = 0.20
SWITCH_OFF_TINT: float = 0.12
CONTROL_WIDTH: int = 32
CONTROL_HEIGHT: int = 28
CONTROL_RADIUS: int = 5


class CompactStyle:
    """Own Tk image lifetimes and visual styles for one root main thread.

    Attributes:
        scale (float): Physical pixels per 96-DPI logical pixel.
        foreground (str): Current Windows system foreground color.
        secondary (str): Current Windows secondary text color.
        background (str): Current Windows window surface color.
        accent (str): Windows selection color used only for small indicators.
        panel (str): Lightly lifted settings surface derived from system colors.
    """

    def __init__(self, root: tk.Tk) -> None:
        """Prepare scalable images and styles without changing OS preferences.

        Args:
            root (tk.Tk): Owning root on the Tk main thread.

        Returns:
            None: Images remain alive as long as this presentation object does.
        """
        self._root: tk.Tk = root
        self.scale: float = root.winfo_fpixels("1i") / REFERENCE_DPI
        self.foreground: str = self._system_color("SystemWindowText", "#242c38")
        self.secondary: str = self._system_color("SystemGrayText", "#657080")
        self.background: str = self._system_color("SystemButtonFace", "#eef0f3")
        self.accent: str = self._system_color("SystemHighlight", "#426b91")
        window: str = self._system_color("SystemWindow", "#ffffff")
        self.panel: str = self._blend(window, self.background, PANEL_LIFT)
        chrome: str = self._blend(self.accent, self.panel, SELECTED_TINT)
        line: str = self._blend(self.foreground, self.panel, FIELD_LINE_TINT)
        self._icons: dict[IconName, ImageTk.PhotoImage] = {}
        self._controls: dict[
            tuple[IconName, ControlState, bool], ImageTk.PhotoImage
        ] = {}
        self._switches: list[ImageTk.PhotoImage] = []
        style: ttk.Style = ttk.Style(root)
        # Clam permits flat geometry while system colors retain Windows color
        # and high-contrast preferences. No native theme setting is modified.
        style.theme_use("clam")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
            font.nametofont(name, root=root).configure(
                family="Segoe UI", size=10
            )
        style.configure(".", background=self.background,
                        foreground=self.foreground)
        style.configure("TFrame", background=self.background)
        style.configure("Panel.TFrame", background=self.panel)
        style.configure("TLabel", background=self.panel)
        style.configure("Title.TLabel", font=("Segoe UI", 12, "bold"),
                        background=self.background)
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"),
                        background=self.background)
        style.configure("PageTitle.TLabel", font=("Segoe UI", 10, "bold"),
                        background=self.panel)
        style.configure("Secondary.TLabel", foreground=self.secondary,
                        background=self.background)
        style.configure("TButton", padding=(8, 4), background=self.background,
                        borderwidth=0, relief="flat")
        style.map("TButton", background=[("active", chrome)])
        style.configure("Icon.TButton", padding=0)
        style.configure("Panel.Icon.TButton", background=self.panel)
        # Image controls carry their own rounded hover/selection/focus marks.
        # Remove the native dotted focus box, retaining native button input.
        image_button_layout: list[StyleNode] = [
            ("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"}),
            ]}),
        ]
        style.layout("Icon.TButton", image_button_layout)
        style.layout("Help.TButton", image_button_layout)
        style.configure("Help.TButton", padding=0, borderwidth=0,
                        relief="flat", foreground=self.secondary,
                        background=self.panel)
        style.map("Icon.TButton", background=[("active", self.background)])
        for button in ("Help.TButton", "Panel.Icon.TButton"):
            style.map(button, background=[("active", self.panel)])
        for field in ("TEntry", "TSpinbox", "TCombobox"):
            style.configure(field, padding=(6, 4), fieldbackground=window,
                            bordercolor=line, lightcolor=self.panel,
                            darkcolor=self.panel, relief="flat",
                            arrowcolor=self.secondary, arrowsize=self.pixels(12))
            style.map(field, bordercolor=[("focus", self.accent)],
                      fieldbackground=[("readonly", window), ("!disabled", window)],
                      background=[("readonly", window), ("!disabled", window)],
                      foreground=[("disabled", self.secondary),
                                  ("!disabled", self.foreground)])
        # Keep Tk's native notebook layout: its tab/client elements also own
        # geometry and hit testing. Conceal their edges with matching colors.
        style.configure("TNotebook", background=self.panel, borderwidth=0,
                        bordercolor=self.panel, lightcolor=self.panel,
                        darkcolor=self.panel,
                        tabmargins=(4, 4, 4, 3))
        style.configure("TNotebook.Tab", padding=(3, 2),
                        background=self.panel, borderwidth=0,
                        bordercolor=self.panel, lightcolor=self.panel,
                        darkcolor=self.panel, focuscolor=self.panel)
        style.map("TNotebook.Tab", background=[("selected", self.panel),
                                              ("active", self.panel)],
                  bordercolor=[("selected", self.panel)],
                  lightcolor=[("selected", self.panel)])
        style.layout("Mode.TRadiobutton", style.layout("Toolbutton"))
        style.configure("Mode.TRadiobutton", padding=0,
                        background=self.panel, borderwidth=0, relief="flat")
        style.map("Mode.TRadiobutton",
                  background=[("selected", self.panel), ("active", self.panel)],
                  relief=[("selected", "flat"), ("!selected", "flat")])
        self._install_switch_style(style)

    def _blend(self, front: str, back: str, opacity: float) -> str:
        """Mix system colors to suggest light layers without window opacity.

        Args:
            front (str): Foreground hexadecimal RGB color.
            back (str): Underlying hexadecimal RGB color.
            opacity (float): Foreground fraction from zero through one.

        Returns:
            str: An opaque RGB color preserving the selected system palette.
        """
        channels: list[str] = []
        for index in (1, 3, 5):
            front_channel: int = int(front[index:index + 2], 16)
            back_channel: int = int(back[index:index + 2], 16)
            value: int = round(
                front_channel * opacity + back_channel * (1 - opacity)
            )
            channels.append(f"{value:02x}")
        return "#" + "".join(channels)

    def _system_color(self, name: str, fallback: str) -> str:
        """Resolve Windows colors, with a portable Tk-test palette fallback.

        Args:
            name (str): Tk's Windows system-color name.
            fallback (str): Color for Tk builds without Windows system colors.

        Returns:
            str: A hexadecimal RGB color usable by Tk and Pillow.
        """
        try:
            channels: tuple[int, int, int] = self._root.winfo_rgb(name)
        except tk.TclError:
            return fallback
        return "#" + "".join(f"{channel // 257:02x}" for channel in channels)

    def pixels(self, logical: int) -> int:
        """Convert a logical control dimension to current physical pixels.

        Args:
            logical (int): Size in pixels at the reference 96-DPI scale.

        Returns:
            int: Rounded, positive physical pixel size.
        """
        return max(1, round(logical * self.scale))

    def icon(self, name: IconName) -> ImageTk.PhotoImage:
        """Return a cached anti-aliased local line icon.

        Args:
            name (IconName): Semantic icon key from the maintained geometry.

        Returns:
            ImageTk.PhotoImage: Main-thread Tk image owned by this object.
        """
        if name not in self._icons:
            size: int = self.pixels(ICON_SIZE)
            image: Image.Image = self._icon_bitmap(
                name, size * IMAGE_SUPERSAMPLING, self.foreground
            )
            self._icons[name] = ImageTk.PhotoImage(
                image.resize((size, size), Image.Resampling.LANCZOS),
                master=self._root,
            )
        return self._icons[name]

    def _icon_bitmap(self, name: IconName, size: int, color: str) -> Image.Image:
        """Draw maintained icon geometry at the requested physical resolution.

        Args:
            name (IconName): Semantic icon geometry key.
            size (int): Square output extent in physical pixels.
            color (str): System-derived stroke color.

        Returns:
            Image.Image: Transparent RGBA bitmap, without a native Tk resource.
        """
        factor: float = size / ICON_SIZE
        image: Image.Image = Image.new("RGBA", (size, size))
        draw: ImageDraw.ImageDraw = ImageDraw.Draw(image)
        stroke: int = max(1, round(1.3 * factor))
        for path in ICON_PATHS[name]:
            draw.line(
                [(x * factor, y * factor) for x, y in path],
                fill=color, width=stroke, joint="curve",
            )
        if name in ICON_CIRCLES:
            draw.ellipse(
                tuple(value * factor for value in ICON_CIRCLES[name]),
                outline=color, width=stroke,
            )
        return image

    def control_image(self, name: IconName, state: ControlState,
                      panel: bool = True) -> ImageTk.PhotoImage:
        """Render a rounded icon state with an explicit selection/focus mark.

        Args:
            name (IconName): Semantic icon key.
            state (ControlState): Native control presentation state.
            panel (bool): Whether the control lives on the settings panel.

        Returns:
            ImageTk.PhotoImage: Cached, root-owned state image.
        """
        key: tuple[IconName, ControlState, bool] = (name, state, panel)
        if key not in self._controls:
            scale: float = self.scale * IMAGE_SUPERSAMPLING
            width: int = round(CONTROL_WIDTH * scale)
            height: int = round(CONTROL_HEIGHT * scale)
            image: Image.Image = Image.new("RGBA", (width, height))
            draw: ImageDraw.ImageDraw = ImageDraw.Draw(image)
            surface: str = self.panel if panel else self.background
            selected: bool = state in ("selected", "selected_focus")
            focused: bool = state in ("focus", "selected_focus")
            if selected or focused or state == "hover":
                draw.rounded_rectangle(
                    (scale, scale, width - scale, height - scale),
                    radius=CONTROL_RADIUS * scale,
                    fill=self._blend(self.accent, surface, SELECTED_TINT),
                    outline=self.accent if focused else None,
                    width=max(1, round(scale)),
                )
            if selected:
                draw.rounded_rectangle(
                    (11 * scale, 25 * scale, 21 * scale, 26 * scale),
                    radius=scale / 2, fill=self.accent,
                )
            icon_size: int = round(ICON_SIZE * scale)
            icon: Image.Image = self._icon_bitmap(
                name, icon_size,
                self.secondary if state == "disabled" else self.foreground,
            )
            image.alpha_composite(
                icon, ((width - icon_size) // 2, (height - icon_size) // 2)
            )
            self._controls[key] = ImageTk.PhotoImage(
                image.resize(
                    (self.pixels(CONTROL_WIDTH), self.pixels(CONTROL_HEIGHT)),
                    Image.Resampling.LANCZOS,
                ), master=self._root,
            )
        return self._controls[key]

    def control_images(self, name: IconName, panel: bool = True) -> tuple[str, ...]:
        """Supply native ttk image states without replacing widget semantics.

        Args:
            name (IconName): Semantic action or tab icon.
            panel (bool): Whether to use the settings-panel surface.

        Returns:
            tuple[str, ...]: Default image followed by state/image pairs.
        """
        return (
            str(self.control_image(name, "normal", panel)),
            "disabled", str(self.control_image(name, "disabled", panel)),
            "selected focus", str(self.control_image(name, "selected_focus", panel)),
            "focus", str(self.control_image(name, "focus", panel)),
            "selected", str(self.control_image(name, "selected", panel)),
            "active", str(self.control_image(name, "hover", panel)),
        )

    def _install_switch_style(self, style: ttk.Style) -> None:
        """Render switch indicators while retaining native checkbutton input.

        Args:
            style (ttk.Style): Root-owned style registry.

        Returns:
            None: Space, invoke, disabled and variable semantics stay native.
        """
        for selected, disabled in ((False, False), (True, False),
                                   (False, True), (True, True)):
            factor: float = self.scale * IMAGE_SUPERSAMPLING
            width: int = math.ceil(SWITCH_WIDTH * factor)
            height: int = math.ceil(SWITCH_HEIGHT * factor)
            image: Image.Image = Image.new("RGBA", (width, height))
            draw: ImageDraw.ImageDraw = ImageDraw.Draw(image)
            color: str = self.accent if selected and not disabled else self.secondary
            draw.rounded_rectangle(
                (0, 0, width - 1, height - 1), radius=height / 2,
                fill=self._blend(color, self.panel, SWITCH_ACTIVE_TINT)
                if selected else self._blend(
                    self.foreground, self.panel, SWITCH_OFF_TINT
                ),
            )
            left: float = (16 if selected else 4) * factor
            draw.ellipse(
                (left, 4 * factor, left + 8 * factor, 12 * factor),
                fill=color,
            )
            self._switches.append(ImageTk.PhotoImage(
                image.resize(
                    (self.pixels(SWITCH_WIDTH), self.pixels(SWITCH_HEIGHT)),
                    Image.Resampling.LANCZOS,
                ), master=self._root,
            ))
        style.element_create(
            "CompactSwitch.indicator", "image", self._switches[0],
            ("disabled", "selected", self._switches[3]),
            ("disabled", self._switches[2]),
            ("selected", self._switches[1]),
            width=self.pixels(SWITCH_WIDTH), sticky="w",
        )
        style.layout("Switch.TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("CompactSwitch.indicator", {"side": "left"}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w",
                    "children": [("Checkbutton.label", {"sticky": "nswe"})]}),
            ]}),
        ])
        style.configure("Switch.TCheckbutton", padding=(0, 5),
                        background=self.background)
        style.configure("Indicator.Switch.TCheckbutton", background=self.panel)
        for name, surface in (("Switch.TCheckbutton", self.background),
                              ("Indicator.Switch.TCheckbutton", self.panel)):
            style.map(name, background=[("disabled", surface), ("active", surface)],
                      foreground=[("disabled", self.secondary)])
        # Keep the native text option as the control's semantic label while
        # rendering a switch next to a separate, aligned field caption.
        style.layout("Indicator.Switch.TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Checkbutton.focus", {"sticky": "nswe", "children": [
                    ("CompactSwitch.indicator", {"sticky": "w"}),
                ]}),
            ]}),
        ])
