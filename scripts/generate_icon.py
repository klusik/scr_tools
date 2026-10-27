# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: scripts/generate_icon.py
# Module Type: Maintained resource generator
# Purpose: Rebuild the original screen-and-cursor application icon.
# Responsibilities: Render matching vector artwork into PNG and ICO assets.
# Author: Rudolf Klusal
# License: MIT

"""Generate reproducible icon resources from simple, original geometry."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT: Path = Path(__file__).resolve().parents[1]
ASSETS: Path = ROOT / "assets" / "icons"
ICON_SIZES: tuple[int, ...] = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SOURCE_SIZE: int = 1024
GEOMETRY_SIZE: int = 256
BACKGROUND: str = "#0B6BCB"
SCREEN: str = "#ECF6FF"
CURSOR: str = "#FFFFFF"
OUTLINE: str = "#08365E"


def render_icon(size: int) -> Image.Image:
    """Draw the icon with supersampling for clean small-size edges.

    Args:
        size (int): Square output dimension in physical pixels.

    Returns:
        Image.Image: A new RGBA image owned by the caller.

    Raises:
        ValueError: If the requested size is not positive.
    """
    if size <= 0:
        raise ValueError("Icon size must be positive.")
    scale: int = SOURCE_SIZE // GEOMETRY_SIZE
    canvas: Image.Image = Image.new(
        "RGBA", (SOURCE_SIZE, SOURCE_SIZE), (0, 0, 0, 0)
    )
    drawing: ImageDraw.ImageDraw = ImageDraw.Draw(canvas)
    drawing.rounded_rectangle(
        (8 * scale, 8 * scale, 248 * scale, 248 * scale),
        radius=52 * scale,
        fill=BACKGROUND,
    )
    drawing.rounded_rectangle(
        (39 * scale, 49 * scale, 217 * scale, 177 * scale),
        radius=14 * scale,
        outline=SCREEN,
        width=12 * scale,
    )
    drawing.line(
        ((128 * scale, 177 * scale), (128 * scale, 205 * scale)),
        fill=SCREEN,
        width=12 * scale,
    )
    drawing.line(
        ((93 * scale, 206 * scale), (163 * scale, 206 * scale)),
        fill=SCREEN,
        width=12 * scale,
    )
    pointer: tuple[tuple[int, int], ...] = (
        (135, 101), (139, 190), (160, 171), (181, 209),
        (202, 197), (180, 159), (208, 153),
    )
    points: list[tuple[int, int]] = [
        (x * scale, y * scale) for x, y in pointer
    ]
    drawing.polygon(points, fill=CURSOR)
    drawing.line(
        points + [points[0]],
        fill=OUTLINE,
        width=6 * scale,
        joint="curve",
    )
    rendered: Image.Image = canvas.resize(
        (size, size), resample=Image.Resampling.LANCZOS
    )
    canvas.close()
    return rendered


def main() -> None:
    """Write the maintained PNG preview and all required ICO resolutions.

    Returns:
        None: Files are written in ``assets/icons``.

    Raises:
        OSError: If the asset directory or files cannot be written.
    """
    ASSETS.mkdir(parents=True, exist_ok=True)
    with render_icon(256) as image:
        image.save(ASSETS / "scr_tools.png", format="PNG")
        image.save(
            ASSETS / "scr_tools.ico",
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
        )
    print("Generated assets/icons/scr_tools.png and scr_tools.ico.")


if __name__ == "__main__":
    main()
