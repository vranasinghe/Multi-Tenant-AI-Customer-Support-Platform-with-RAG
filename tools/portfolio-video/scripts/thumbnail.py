"""Thumbnail and portfolio cover: editable SVG with real screenshot frames, rendered by Chrome.

    python scripts/thumbnail.py

Needs opencv-python. Set CHROME_PATH if Chrome is not in the default place.
"""

from __future__ import annotations

import base64
import os
import pathlib
import subprocess
import tempfile

import cv2

APP = pathlib.Path(__file__).resolve().parents[1]
FINAL = APP.parents[1] / "output/video/final"
CHROME = os.environ.get("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def shot(clip: str, second: float, box: tuple[int, int, int, int]) -> str:
    capture = cv2.VideoCapture(str(APP / "public/footage" / f"{clip}.mp4"))
    capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
    ok, image = capture.read()
    if not ok:
        raise SystemExit(f"cannot read {clip} at {second} s")
    x, y, w, h = box
    ok, png = cv2.imencode(".png", image[y : y + h, x : x + w])
    return "data:image/png;base64," + base64.b64encode(png.tobytes()).decode()


def font(weight: int) -> str:
    name = f"inter-latin-{weight}-normal.woff2"
    data = (APP / "node_modules/@fontsource/inter/files" / name).read_bytes()
    return (
        "@font-face{font-family:Inter;font-weight:%d;src:url(data:font/woff2;base64,%s)}"
        % (weight, base64.b64encode(data).decode())
    )


def window(x: int, y: int, w: int, h: int, image: str, ident: str) -> str:
    return f"""<g id="{ident}">
  <rect x="{x - 8}" y="{y - 34}" width="{w + 16}" height="{h + 42}" rx="16" fill="#111827" stroke="#2563EB" stroke-width="2"/>
  <circle cx="{x + 10}" cy="{y - 17}" r="5" fill="#EF4444"/><circle cx="{x + 28}" cy="{y - 17}" r="5" fill="#F59E0B"/><circle cx="{x + 46}" cy="{y - 17}" r="5" fill="#22C55E"/>
  <image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" href="{image}"/>
</g>"""


def motif() -> str:
    nodes = [(0, "Experience"), (1, "Application"), (2, "Data · Jobs"), (3, "RAG")]
    out = ['<g id="architecture-motif">']
    for i, name in nodes:
        x = 96 + i * 190
        out.append(
            f'<rect x="{x}" y="930" width="160" height="58" rx="12" fill="#111827" stroke="#38BDF8" stroke-width="2"/>'
            f'<text x="{x + 80}" y="967" text-anchor="middle" font-size="22" fill="#FFFFFF" font-weight="500">{name}</text>'
        )
        if i:
            out.append(f'<path d="M{x - 30} 959h30" stroke="#2563EB" stroke-width="4"/>')
    return "".join(out) + "</g>"


def main() -> None:
    FINAL.mkdir(parents=True, exist_ok=True)
    dashboard = shot("R15-dashboard-populated", 2.0, (0, 0, 1340, 780))
    widget = shot("R09-customer-widget", 16.0, (1370, 320, 550, 760))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{{w}}" height="{{h}}" viewBox="0 0 1920 1080" font-family="Inter">
<style>{font(500)}{font(700)}</style>
<defs><radialGradient id="glow" cx="0.75" cy="0.35" r="0.7"><stop offset="0" stop-color="#2563EB" stop-opacity="0.35"/><stop offset="1" stop-color="#080C14" stop-opacity="0"/></radialGradient></defs>
<rect width="1920" height="1080" fill="#080C14"/><rect width="1920" height="1080" fill="url(#glow)"/>
<g id="title" font-weight="700" fill="#FFFFFF">
  <text x="96" y="300" font-size="150" letter-spacing="-3">BEYOND A</text>
  <text x="96" y="460" font-size="150" letter-spacing="-3">CHATBOT</text>
  <rect x="100" y="510" width="360" height="10" rx="5" fill="#2563EB"/>
  <text x="96" y="610" font-size="58" fill="#38BDF8">Multi-Tenant RAG Platform</text>
  <text x="96" y="680" font-size="34" fill="#94A3B8" font-weight="500">An engineering case study</text>
</g>
{window(1010, 150, 820, 478, dashboard, "dashboard")}
{window(1480, 440, 350, 484, widget, "widget")}
{motif()}
</svg>"""
    for name, width, height in (("thumbnail-1280x720", 1280, 720), ("portfolio-cover-1920x1080", 1920, 1080)):
        source = FINAL / f"{name}.svg"
        source.write_text(svg.replace("{w}", str(width)).replace("{h}", str(height)), encoding="utf-8")
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run(
                [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                 f"--user-data-dir={profile}", f"--window-size={width},{height}",
                 f"--screenshot={FINAL / (name + '.png')}", source.as_uri()],
                check=True, capture_output=True, timeout=120,
            )
        image = cv2.imread(str(FINAL / f"{name}.png"))
        print(name, image.shape[1], "x", image.shape[0])


if __name__ == "__main__":
    main()
