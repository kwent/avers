"""Generate Avers icon SVGs (brass coin, beaded rim, Didone 'A', laurel) and render the app PNGs.

Run from mobile/:  python3 assets/source/make_icons.py   (needs rsvg-convert: brew install librsvg)
"""

import math
import subprocess
from pathlib import Path

SRC = Path(__file__).parent
ASSETS = SRC.parent

INK = "#17130E"
BG = "#F7F3EA"


def coin(cx=512, cy=512, r=400, mono=False) -> str:
    """Coin artwork centred on (cx, cy) with outer radius r. mono=True gives a flat white glyph."""
    s = r / 400  # all geometry below is designed for r=400 around (512, 512)

    def p(x, y):
        return f"{cx + (x - 512) * s:.1f},{cy + (y - 512) * s:.1f}"

    def poly(points):
        return " ".join(p(x, y) for x, y in points)

    gold = "#fff" if mono else "url(#face)"
    relief = "#fff" if mono else "url(#relief)"
    shadow = "none" if mono else "#5E4210"

    letter = [
        [(497, 318), (538, 318), (686, 694), (606, 694)],  # thick right stroke
        [(500, 318), (520, 318), (384, 694), (364, 694)],  # thin left stroke
        [(418, 560), (628, 560), (634, 578), (412, 578)],  # crossbar
        [(326, 680), (424, 680), (424, 698), (326, 698)],  # left serif
        [(578, 680), (700, 680), (700, 698), (578, 698)],  # right serif
    ]

    leaves = []
    for side in (-1, 1):  # left and right branch, from the bottom of the coin up its sides
        t0, t1, R = math.radians(18), math.radians(118), 300
        # stem: arc along the branch
        sx0, sy0 = 512 + side * R * math.sin(t0), 512 + R * math.cos(t0)
        sx1, sy1 = 512 + side * R * math.sin(t1), 512 + R * math.cos(t1)
        leaves.append(
            f'<path d="M{p(sx0, sy0)} A{R * s:.1f},{R * s:.1f} 0 0 {0 if side > 0 else 1} {p(sx1, sy1)}" '
            f'fill="none" stroke="currentColor" stroke-width="{6 * s:.1f}" stroke-linecap="round"/>'
        )
        for i in range(9):
            t = t0 + (t1 - t0) * (i + 0.5) / 9
            x, y = 512 + side * R * math.sin(t), 512 + R * math.cos(t)
            # direction of growth (up the branch) and the outward normal
            dx, dy = side * math.cos(t), -math.sin(t)
            nx, ny = side * math.sin(t), math.cos(t)
            heading = math.degrees(math.atan2(dy, dx))
            for k in (1, -1):  # outer and inner leaf, splayed forward into a V
                lx, ly = x + nx * 15 * k + dx * 10, y + ny * 15 * k + dy * 10
                X, Y = cx + (lx - 512) * s, cy + (ly - 512) * s
                angle = heading - k * side * 38
                leaves.append(
                    f'<ellipse cx="{X:.1f}" cy="{Y:.1f}" rx="{25 * s:.1f}" ry="{9 * s:.1f}" '
                    f'transform="rotate({angle:.1f} {X:.1f} {Y:.1f})"/>'
                )
    beads = "".join(
        f'<circle cx="{cx + 362 * s * math.cos(t):.1f}" cy="{cy + 362 * s * math.sin(t):.1f}" r="{7.5 * s:.1f}"/>'
        for t in (2 * math.pi * k / 84 for k in range(84))
    )

    if mono:
        return (
            f'<g fill="#fff" color="#fff"><circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#fff" stroke-width="{26 * s:.1f}"/>'
            f"{beads}" + "".join(f'<polygon points="{poly(pts)}"/>' for pts in letter) + "".join(leaves) + "</g>"
        )

    defs = f"""
  <radialGradient id="face" cx="40%" cy="35%" r="75%">
    <stop offset="0" stop-color="#F6DE97"/><stop offset="0.45" stop-color="#D9AE52"/>
    <stop offset="0.85" stop-color="#A97A27"/><stop offset="1" stop-color="#8C6219"/>
  </radialGradient>
  <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#FBE7A9"/><stop offset="0.5" stop-color="#B8862F"/><stop offset="1" stop-color="#6E4C12"/>
  </linearGradient>
  <linearGradient id="relief" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#FFF1C4"/><stop offset="1" stop-color="#C39338"/>
  </linearGradient>"""

    def embossed(shapes: str) -> str:
        # dark copy offset down-right, then the lit relief on top
        return (
            f'<g fill="{shadow}" color="{shadow}" transform="translate({5 * s:.1f} {6 * s:.1f})" opacity="0.85">'
            f"{shapes}</g>"
            f'<g fill="{relief}" color="#E9C46F">{shapes}</g>'
        )

    letter_svg = "".join(f'<polygon points="{poly(pts)}"/>' for pts in letter)
    return f"""<defs>{defs}</defs>
  <circle cx="{cx}" cy="{cy + 14 * s:.1f}" r="{r}" fill="#000" opacity="0.35"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#rim)"/>
  <circle cx="{cx}" cy="{cy}" r="{r - 24 * s:.1f}" fill="{gold}"/>
  <circle cx="{cx}" cy="{cy}" r="{r - 24 * s:.1f}" fill="none" stroke="#7A5616" stroke-width="{3 * s:.1f}" opacity="0.6"/>
  {embossed(beads)}
  {embossed("".join(leaves))}
  {embossed(letter_svg)}"""


def svg(body: str, background: str | None = None) -> str:
    bg = ""
    if background == "ink":
        bg = (
            '<defs><radialGradient id="bg" cx="50%" cy="40%" r="75%"><stop offset="0" stop-color="#3A3024"/>'
            f'<stop offset="1" stop-color="{INK}"/></radialGradient></defs><rect width="1024" height="1024" fill="url(#bg)"/>'
        )
    elif background:
        bg = f'<rect width="1024" height="1024" fill="{background}"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">{bg}{body}</svg>\n'


def render(name: str, content: str, size: int, out: str):
    path = SRC / f"{name}.svg"
    path.write_text(content)
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(path), "-o", str(ASSETS / out)], check=True)


if __name__ == "__main__":
    render("icon", svg(coin(r=392), background="ink"), 1024, "icon.png")
    # Android adaptive icon: artwork must sit inside the central 66% safe zone
    render("android-foreground", svg(coin(r=300)), 1024, "android-icon-foreground.png")
    render("android-background", svg("", background=INK), 1024, "android-icon-background.png")
    render("android-monochrome", svg(coin(r=300, mono=True)), 1024, "android-icon-monochrome.png")
    render("splash", svg(coin(r=420)), 1024, "splash-icon.png")
    render("favicon", svg(coin(r=480), background=None), 48, "favicon.png")
    # iOS rejects icons with an alpha channel
    subprocess.run(["magick", str(ASSETS / "icon.png"), "-alpha", "off", str(ASSETS / "icon.png")], check=True)
    print("icons rendered")
