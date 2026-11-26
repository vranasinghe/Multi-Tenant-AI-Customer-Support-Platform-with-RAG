"""Does a finished MP4 match the current composition?

    python scripts/match.py <video.mp4> <folder of stills named by frame number>

Render the stills from the current source with scripts/stills.mjs, then compare each with the
same frame of the MP4. A stale chapter or a shifted join shows up as a large difference.
"""

from __future__ import annotations

import json
import pathlib
import sys

import cv2
import numpy as np


def main(video: str, folder: str) -> int:
    stills = {int(p.stem): p for p in pathlib.Path(folder).glob("[0-9]*.png")}
    capture = cv2.VideoCapture(video)
    index, results = 0, []
    while True:
        ok, image = capture.read()
        if not ok:
            break
        if index in stills:
            still = cv2.imread(str(stills[index]))
            difference = cv2.absdiff(image, still).max(axis=2)
            # Share of pixels that differ clearly: compression noise stays well below this.
            results.append((index, round(float((difference > 48).mean()) * 100, 3)))
        index += 1
    worst = sorted(results, key=lambda item: -item[1])
    bad = [item for item in results if item[1] > 0.25]
    print(json.dumps({"compared": len(results), "requested": len(stills),
                      "worstPercentDiffering": worst[:5], "mismatched": bad}))
    return 1 if bad or len(results) != len(stills) else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(*sys.argv[1:]))
