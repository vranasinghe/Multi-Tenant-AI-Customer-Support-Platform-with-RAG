"""Frame-level inspection of a finished MP4 against its generated script.

    python scripts/inspect_video.py <video.mp4> <script.json> <out folder>

Reads every frame once. Writes one frame per subtitle cue (taken at its midpoint, so footage,
narration and burned-in caption can be judged together), reports long stretches where nothing but
the progress bar changes, and checks the frames either side of every chapter boundary.
"""

from __future__ import annotations

import json
import pathlib
import sys

import cv2
import numpy as np


def main(video: str, script: str, out: str) -> None:
    data = json.loads(pathlib.Path(script).read_text(encoding="utf-8"))
    folder = pathlib.Path(out)
    (folder / "cues").mkdir(parents=True, exist_ok=True)
    wanted = {
        min(round((c["start"] + c["end"]) / 2 * 30), data["frames"] - 1): i
        for i, c in enumerate(data["captions"], 1)
    }
    starts = {}
    for segment in data["segments"]:
        starts.setdefault(segment["chapter"], segment["from"])
    edges = {f + d: f for f in starts.values() if f for d in (-1, 0, 20, 60)}

    capture = cv2.VideoCapture(video)
    index, previous, run_start, still, edge_tiles = 0, None, 0, [], []
    while True:
        ok, image = capture.read()
        if not ok:
            break
        # Content band only: the caption, watermark and progress bar are excluded.
        content = cv2.cvtColor(cv2.resize(image, (480, 270)), cv2.COLOR_BGR2GRAY)[18:226]
        changed = previous is None or int((cv2.absdiff(content, previous) > 12).sum()) > 12
        if changed:
            if index - run_start > 150:
                still.append((run_start, index - run_start))
            run_start = index
            previous = content
        if index in wanted:
            cv2.imwrite(str(folder / "cues" / f"{wanted[index]:03}-{index:05}.png"), image)
        if index in edges:
            tile = cv2.resize(image, (480, 270), interpolation=cv2.INTER_AREA)
            cv2.putText(tile, f"{index}", (6, 262), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            edge_tiles.append(tile)
        index += 1
    if index - run_start > 150:
        still.append((run_start, index - run_start))

    if edge_tiles:
        while len(edge_tiles) % 4:
            edge_tiles.append(np.zeros((270, 480, 3), np.uint8))
        sheet = np.vstack([np.hstack(edge_tiles[i : i + 4]) for i in range(0, len(edge_tiles), 4)])
        cv2.imwrite(str(folder / "chapter-boundaries.png"), sheet)

    def name(frame: int) -> str:
        return [s["id"] for s in data["segments"] if s["from"] <= frame][-1]

    report = {
        "frames": index,
        "expectedFrames": data["frames"],
        "cueFrames": len(wanted),
        "unchangedOver5s": [
            {"segment": name(a), "fromSecond": round(a / 30, 1), "seconds": round(n / 30, 1)}
            for a, n in still
        ],
    }
    (folder / "inspect.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(2)
    main(*sys.argv[1:])
