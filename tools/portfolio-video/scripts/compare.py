"""Side-by-side stills: the original 80 s preview against the revised one.

    python scripts/compare.py

Reads both finished MP4 files and writes output/video/final/qa/comparison/*.png. Needs
opencv-python.
"""

from __future__ import annotations

import pathlib

import cv2
import numpy as np

FINAL = pathlib.Path(__file__).resolve().parents[3] / "output/video/final"
OUT = FINAL / "qa/comparison"
OLD = FINAL / "showcase-preview.mp4"
NEW = FINAL / "showcase-preview-v2.mp4"

# (file, title, [(second in the original, second in the revision), ...])
IMPROVEMENTS = [
    ("1-opening", "Opening and product montage", [(3, 2), (12, 7), (18, 14)]),
    ("2-architecture", "Architecture", [(46, 50), (52, 59), (55, 63)]),
    ("3-evidence", "Test evidence", [(59, 68), (64, 73), (70, 79)]),
    ("4-demo-reply", "Demonstration: the repeated demo reply", [(27, 24), (33, 30), (40, 41)]),
]


def frame(video: pathlib.Path, second: float) -> np.ndarray:
    capture = cv2.VideoCapture(str(video))
    capture.set(cv2.CAP_PROP_POS_FRAMES, round(second * 30))
    ok, image = capture.read()
    if not ok:
        raise SystemExit(f"cannot read {video.name} at {second} s")
    return cv2.resize(image, (960, 540), interpolation=cv2.INTER_AREA)


def banner(text: str, width: int, height: int = 54) -> np.ndarray:
    image = np.full((height, width, 3), 24, np.uint8)
    cv2.putText(image, text, (18, height - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    gap = np.full((540, 8, 3), 90, np.uint8)
    for name, title, pairs in IMPROVEMENTS:
        rows = [banner(title, 1928)]
        rows.append(np.hstack([banner("ORIGINAL (80 s)", 964), banner("REVISED v2 (90 s)", 964)]))
        for old, new in pairs:
            rows.append(np.hstack([frame(OLD, old), gap, frame(NEW, new)]))
            rows.append(banner(f"original {old} s | revised {new} s", 1928, 40))
        cv2.imwrite(str(OUT / f"{name}.png"), np.vstack(rows))
        print(OUT / f"{name}.png")


if __name__ == "__main__":
    main()
