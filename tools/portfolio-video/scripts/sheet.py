"""Combine a folder of stills into review sheets.

    python scripts/sheet.py <folder> <out prefix> [columns] [per sheet]
"""

from __future__ import annotations

import glob
import pathlib
import sys

import cv2
import numpy as np


def main(folder: str, prefix: str, columns: int = 3, per: int = 12) -> None:
    files = sorted(glob.glob(f"{folder}/*.png"))
    for part, start in enumerate(range(0, len(files), per), 1):
        tiles = []
        for name in files[start : start + per]:
            tile = cv2.resize(cv2.imread(name), (640, 360), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 340), (80, 360), (0, 0, 0), -1)
            cv2.putText(tile, pathlib.Path(name).stem, (4, 355), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.rectangle(tile, (0, 0), (639, 359), (70, 70, 70), 1)
            tiles.append(tile)
        while len(tiles) % columns:
            tiles.append(np.zeros((360, 640, 3), np.uint8))
        rows = [np.hstack(tiles[i : i + columns]) for i in range(0, len(tiles), columns)]
        cv2.imwrite(f"{prefix}-{part}.png", np.vstack(rows))
        print(f"{prefix}-{part}.png")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0], args[1], *[int(a) for a in args[2:]])
