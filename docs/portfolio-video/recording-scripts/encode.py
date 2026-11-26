"""Turn the frames captured by record.cjs into one 30 fps MP4 per clip.

    python encode.py <output dir>

Needs opencv-python. The files are intermediates (MPEG-4 Part 2) for the editor; the final
export is H.264. Portrait clips are centred on the brand background, never stretched.
"""

from __future__ import annotations

import json
import pathlib
import sys

import cv2
import numpy as np

FPS = 30
BACKGROUND = (20, 12, 8)  # #080C14 as BGR


def fit(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    h, w = image.shape[:2]
    scale = min(width / w, height / h)
    nw, nh = int(w * scale), int(h * scale)
    if (nw, nh) != (w, h):
        image = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((height, width, 3), BACKGROUND, dtype=np.uint8)
    top, left = (height - nh) // 2, (width - nw) // 2
    canvas[top : top + nh, left : left + nw] = image
    return canvas


def main(root: pathlib.Path) -> int:
    scale = json.loads((root / "manifest.json").read_text()).get("scale", 1.25)
    size = (3840, 2160) if scale >= 2.5 else (1920, 1080)
    clips = root / "clips"
    clips.mkdir(exist_ok=True)
    for scene in sorted((root / "frames").iterdir()):
        index = json.loads((scene / "index.json").read_text())
        frames = index["frames"]
        if not frames:
            print(f"{scene.name}: no frames, skipped")
            continue
        out = clips / f"{scene.name}.mp4"
        writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, size)
        if not writer.isOpened():
            print(f"{scene.name}: cannot open a video writer")
            return 1
        start, end = frames[0][1], index["end"]
        current, loaded, image = 0, None, None
        for n in range(int((end - start) * FPS) + 1):
            t = start + n / FPS
            while current + 1 < len(frames) and frames[current + 1][1] <= t:
                current += 1
            if loaded != current:
                image = fit(cv2.imread(str(scene / frames[current][0])), size)
                loaded = current
            writer.write(image)
        writer.release()
        print(f"{scene.name}: {end - start:.1f}s {size[0]}x{size[1]} {out.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(pathlib.Path(sys.argv[1])))
