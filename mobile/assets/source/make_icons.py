"""Render every Avers icon asset from the master artwork (assets/source/icon-source.png).

The master was generated with a fake transparency checkerboard baked into its pixels, so the
background is first removed with an edge flood fill (the gray checker is far from the gold
artwork in colour). Run from mobile/:  python3 assets/source/make_icons.py   (needs ImageMagick)
"""

import subprocess
from pathlib import Path

SRC = Path(__file__).parent
ASSETS = SRC.parent
MASTER = SRC / "icon-source.png"
CUTOUT = SRC / "icon-cutout.png"

INK = "#17130E"
INK_LIGHT = "#3A3024"
FUZZ = "25%"


def magick(*args):
    subprocess.run(["magick", *map(str, args)], check=True)


def cutout():
    w = int(subprocess.check_output(["magick", "identify", "-format", "%w", str(MASTER)]))
    seeds = [(0, 0), (w - 1, 0), (0, w - 1), (w - 1, w - 1), (w // 2, 1), (w // 2, w - 2), (1, w // 2), (w - 2, w // 2)]
    fills = [arg for x, y in seeds for arg in ("-draw", f"color {x},{y} floodfill")]
    magick(
        MASTER, "-alpha", "set", "-fuzz", FUZZ, "-fill", "none", *fills,
        # tidy the cut: drop the 1px fringe, then anti-alias the edge
        "-channel", "A", "-morphology", "Erode", "Disk:1", "-blur", "0x0.8", "+channel",
        "-trim", "+repage", CUTOUT,
    )  # fmt: skip


def on_ink(size: int, art: int, out: Path):
    """Artwork centred on the dark radial background, opaque (iOS rejects alpha)."""
    magick(
        "-size", f"{size}x{size}", f"radial-gradient:{INK_LIGHT}-{INK}",
        "(", CUTOUT, "-resize", f"{art}x{art}", ")", "-gravity", "center", "-composite",
        "-alpha", "off", out,
    )  # fmt: skip


def transparent(size: int, art: int, out: Path, *extra):
    magick(CUTOUT, "-resize", f"{art}x{art}", *extra, "-background", "none", "-gravity", "center",
           "-extent", f"{size}x{size}", out)  # fmt: skip


if __name__ == "__main__":
    cutout()
    on_ink(1024, 860, ASSETS / "icon.png")
    # Android adaptive icon: keep the artwork inside the central 66% safe zone
    transparent(1024, 660, ASSETS / "android-icon-foreground.png")
    magick("-size", "1024x1024", f"xc:{INK}", ASSETS / "android-icon-background.png")
    # Themed (monochrome) icon: white silhouette keeping the relief as alpha
    transparent(
        1024, 660, ASSETS / "android-icon-monochrome.png",
        "(", "+clone", "-alpha", "off", "-colorspace", "gray", "-level", "15%,85%", ")",
        "(", "-clone", "0", "-alpha", "extract", ")", "-delete", "0",
        "-compose", "multiply", "-composite", "-background", "white", "-alpha", "shape",
    )  # fmt: skip
    transparent(1024, 1000, ASSETS / "splash-icon.png")
    on_ink(48, 46, ASSETS / "favicon.png")
    print("icons rendered")
