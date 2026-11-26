"""Check a rendered video and write representative evidence next to it.

    python scripts/qa.py ../../output/video/final/showcase-preview.mp4 80

Needs opencv-python. Container properties come from Remotion's bundled ffprobe. Writes
qa/<name>-report.json and qa/<name>-contact.png (one frame every half second, for human review of
privacy, cropping and labels, which no automatic check can judge).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import cv2
import numpy as np

APP = pathlib.Path(__file__).resolve().parents[1]
CLI = APP / "node_modules/@remotion/cli/remotion-cli.js"


def ffprobe(video: pathlib.Path) -> dict:
    out = subprocess.run(
        ["node", str(CLI), "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        cwd=APP, capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out[out.index("{"):])


def main(video: pathlib.Path, expected_seconds: float) -> int:
    probe = ffprobe(video)
    streams = probe["streams"]
    picture = next(s for s in streams if s["codec_type"] == "video")
    audio = [s for s in streams if s["codec_type"] == "audio"]

    capture = cv2.VideoCapture(str(video))
    decoded, blank, jumps, tiles = 0, [], [], []
    previous = None
    while True:
        ok, image = capture.read()
        if not ok:
            break
        small = cv2.resize(image, (192, 108), interpolation=cv2.INTER_AREA)
        # Content band only: labels and the watermark are on every frame.
        content = small[10:100]
        if float(content.std()) < 4:
            blank.append(decoded)
        if previous is not None and float(np.mean(cv2.absdiff(small, previous))) > 45:
            jumps.append(decoded)
        previous = small
        if decoded % 15 == 0:
            tile = cv2.resize(image, (384, 216), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 200), (62, 216), (0, 0, 0), -1)
            cv2.putText(tile, f"{decoded}", (4, 212), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
            tiles.append(tile)
        decoded += 1

    columns = 6
    while len(tiles) % columns:
        tiles.append(np.zeros((216, 384, 3), np.uint8))
    sheet = np.vstack([np.hstack(tiles[i:i + columns]) for i in range(0, len(tiles), columns)])
    qa = video.parent / "qa"
    qa.mkdir(exist_ok=True)
    cv2.imwrite(str(qa / f"{video.stem}-contact.png"), sheet)
    for part in range(0, len(tiles), 54):
        rows = tiles[part:part + 54]
        cv2.imwrite(
            str(qa / f"{video.stem}-contact-{part // 54 + 1}.png"),
            np.vstack([np.hstack(rows[i:i + columns]) for i in range(0, len(rows), columns)]),
        )

    rate = picture["r_frame_rate"]
    report = {
        "file": video.name,
        "bytes": video.stat().st_size,
        "seconds": float(probe["format"]["duration"]),
        "width": picture["width"],
        "height": picture["height"],
        "frameRate": rate,
        "videoCodec": picture["codec_name"],
        "profile": picture.get("profile"),
        "pixelFormat": picture.get("pix_fmt"),
        "audioStreams": [s["codec_name"] for s in audio],
        "decodedFrames": decoded,
        "blankFrames": blank,
        "largeJumps": jumps,
    }
    checks = {
        "1920x1080": (picture["width"], picture["height"]) == (1920, 1080),
        "30 fps": rate == "30/1",
        "H.264": picture["codec_name"] == "h264",
        "frame count": decoded == round(expected_seconds * 30),
        "duration": abs(report["seconds"] - expected_seconds) < 0.2,
        # The scripted fade to the background at the very end is the only allowed empty stretch.
        "no unintended empty frames": all(f >= decoded - 4 for f in blank),
    }
    report["checks"] = checks
    (qa / f"{video.stem}-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(pathlib.Path(sys.argv[1]).resolve(), float(sys.argv[2])))
