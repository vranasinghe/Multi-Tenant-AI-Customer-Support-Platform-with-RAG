"""Check the final MP4 files themselves and write the evidence under output/video/final.

    .venv-tts/Scripts/python.exe scripts/final_qa.py

Covers container and stream properties, full decoding, frame counts, black and frozen stretches,
loudness and true peak of the delivered audio, speech recognition of that audio against the
narration, subtitle sanity, contact sheets and one review still per subtitle cue. What needs eyes
and ears is not marked as passed here.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib
import re
import subprocess
import sys

import cv2
import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.signal import resample_poly

APP = pathlib.Path(__file__).resolve().parents[1]
ROOT = APP.parents[1]
FINAL = ROOT / "output/video/final"
CLI = APP / "node_modules/@remotion/cli/remotion-cli.js"
NAMES = {"showcase": ("showcase-v2", (85, 110)), "documentary": ("documentary", (660, 780))}


def tool(name: str, *args: str) -> str:
    done = subprocess.run(["node", str(CLI), name, *args], cwd=APP, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=True)
    return done.stdout + done.stderr


def words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def inspect_picture(path: pathlib.Path, cue_frames: dict[int, int], stills: pathlib.Path | None):
    capture = cv2.VideoCapture(str(path))
    index, black, previous, run, frozen, tiles = 0, [], None, 0, [], []
    while True:
        ok, image = capture.read()
        if not ok:
            break
        small = cv2.cvtColor(cv2.resize(image, (480, 270)), cv2.COLOR_BGR2GRAY)
        content = small[18:226]
        if float(content.std()) < 4:
            black.append(index)
        if previous is None or int((cv2.absdiff(content, previous) > 12).sum()) > 12:
            if index - run > 240:
                frozen.append((run, index - run))
            run, previous = index, content
        if index % 150 == 0:
            tile = cv2.resize(image, (384, 216), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 0), (96, 20), (0, 0, 0), -1)
            cv2.putText(tile, f"{index // 1800}:{index // 30 % 60:02}", (4, 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            tiles.append(tile)
        if stills is not None and index in cue_frames:
            cv2.imwrite(str(stills / f"{cue_frames[index]:03}-{index:05}.jpg"), image,
                        [cv2.IMWRITE_JPEG_QUALITY, 88])
        index += 1
    if index - run > 240:
        frozen.append((run, index - run))
    while len(tiles) % 5:
        tiles.append(np.zeros((216, 384, 3), np.uint8))
    for part in range(0, len(tiles), 40):
        block = tiles[part : part + 40]
        cv2.imwrite(str(FINAL / "contact-sheets" / f"{path.stem}-{part // 40 + 1}.png"),
                    np.vstack([np.hstack(block[i : i + 5]) for i in range(0, len(block), 5)]))
    return index, black, frozen


def black_runs(frames: list[int]) -> list[tuple[int, int]]:
    runs: list[list[int]] = []
    for f in frames:
        if runs and f == runs[-1][0] + runs[-1][1]:
            runs[-1][1] += 1
        else:
            runs.append([f, 1])
    return [(a, n) for a, n in runs]


def audio_check(path: pathlib.Path, cues: list[dict], asr) -> dict:
    wav = FINAL / "reports" / f"{path.stem}.wav"
    tool("ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-c:a", "pcm_s24le", str(wav))
    audio, rate = sf.read(wav)
    meter = pyloudnorm.Meter(rate)
    result = {
        "integratedLUFS": round(meter.integrated_loudness(audio), 2),
        "truePeakDBTP": round(float(20 * np.log10(np.abs(resample_poly(audio, 4, 1, axis=0)).max())), 2),
        "clippedSamples": int((np.abs(audio) >= 0.9999).sum()),
        "decodedAudioSha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
    }
    # Longest stretch where the whole mix is practically silent (music should never drop out).
    block = rate // 10
    level = np.sqrt((audio[: len(audio) // block * block].reshape(-1, block, 2) ** 2).mean(axis=(1, 2)))
    quiet, longest = 0, 0
    for value in level[20:-30]:
        quiet = quiet + 1 if value < 10 ** (-60 / 20) else 0
        longest = max(longest, quiet)
    result["longestSilenceSeconds"] = longest / 10
    if asr is not None:
        heard = []
        for segment in asr.transcribe(str(wav), beam_size=5, word_timestamps=True)[0]:
            heard += [(w, float(x.start)) for x in segment.words for w in words(x.word)]
        script = []
        for cue in cues:
            script += [(w, cue["at"], cue["name"]) for w in words(cue["text"])]
        matcher = difflib.SequenceMatcher(None, [s[0] for s in script], [h[0] for h in heard],
                                          autojunk=False)
        matched = set()
        offsets = []
        for i, j, size in matcher.get_matching_blocks():
            for k in range(size):
                matched.add(i + k)
                name = script[i + k][2]
                if i + k == 0 or script[i + k - 1][2] != name:
                    offsets.append(abs(heard[j + k][1] - script[i + k][1]))
        by_cue: dict[str, list[bool]] = {}
        for n, (_, _, name) in enumerate(script):
            by_cue.setdefault(name, []).append(n in matched)
        result["recognition"] = {
            "wordsRecognised": round(len(matched) / len(script), 3),
            "narrationPartsUnderHalfRecognised": [k for k, v in by_cue.items() if sum(v) < len(v) / 2],
            "partsStartChecked": len(offsets),
            "medianStartDifferenceSeconds": round(float(np.median(offsets)), 3),
            "maxStartDifferenceSeconds": round(float(max(offsets)), 3),
        }
    wav.unlink()
    return result


def frame_count(path: pathlib.Path) -> int:
    capture = cv2.VideoCapture(str(path))
    n = 0
    while capture.grab():
        n += 1
    return n


def privacy() -> dict:
    """The one known exposure: original R08 frames 204-237 must not be in the working copy."""
    original = frame_count(ROOT / "output/video/portfolio/clips/R08-activate-and-install.mp4")
    proxy = frame_count(APP / "public/footage/R08-activate-and-install.mp4")
    sources = "".join(f.read_text(encoding="utf-8") for f in (APP / "src").rglob("*.ts*"))
    return {
        "r08OriginalFrames": original,
        "r08WorkingCopyFrames": proxy,
        "removedFrames": original - proxy,
        "compositionsReferenceOriginalClips": "portfolio/clips" in sources,
        "passed": original - proxy == 34 and "portfolio/clips" not in sources,
    }


def web_captions(video: str) -> None:
    srt = (FINAL / f"{video}-final.en.srt").read_text(encoding="utf-8")
    body = re.sub(r"(\d\d:\d\d:\d\d),(\d{3})", r"\1.\2", srt)
    (FINAL / f"{video}-final.en.vtt").write_text("WEBVTT\n\n" + body, encoding="utf-8")


def phone_sheet(video: str) -> None:
    """Review stills scaled to a phone's width, for judging small text by eye."""
    files = sorted((FINAL / "review-stills" / video).glob("*.jpg"))
    picked = files[:: max(len(files) // 12, 1)][:12]
    tiles = [cv2.resize(cv2.imread(str(f)), (390, 219), interpolation=cv2.INTER_AREA) for f in picked]
    while len(tiles) % 3:
        tiles.append(np.zeros((219, 390, 3), np.uint8))
    cv2.imwrite(str(FINAL / "contact-sheets" / f"{video}-phone-width.png"),
                np.vstack([np.hstack(tiles[i : i + 3]) for i in range(0, len(tiles), 3)]))


def main() -> int:
    from faster_whisper import WhisperModel

    asr = WhisperModel("small.en", device="cpu", compute_type="int8",
                       download_root=str(APP / ".cache-tts/whisper"))
    for folder in ("contact-sheets", "review-stills", "reports"):
        (FINAL / folder).mkdir(parents=True, exist_ok=True)
    report: dict = {"videos": {}, "privacy": privacy()}
    for video, (data, (low, high)) in NAMES.items():
        script = json.loads((APP / "src/data/generated" / f"{data}.json").read_text(encoding="utf-8"))
        cues = json.loads((APP / f"narration/audio/{video}-cues.json").read_text(encoding="utf-8"))
        seconds = script["frames"] / 30
        captions = script["captions"]
        srt = (FINAL / f"{video}-final.en.srt").read_text(encoding="utf-8")
        report[f"{video}-subtitles"] = {
            "cues": len(captions), "srtCues": srt.count("-->"),
            "overlaps": sum(a["end"] > b["start"] + 0.001 for a, b in zip(captions, captions[1:])),
            "pastEnd": sum(c["end"] > seconds for c in captions),
            "overTwoLines": sum(c["text"].count("\n") > 1 for c in captions),
            "shorterThanOneSecond": sum(c["end"] - c["start"] < 1 for c in captions),
        }
        web_captions(video)
        midpoints = {int((c["start"] + c["end"]) * 15): i for i, c in enumerate(captions, 1)}
        for suffix in ("", "-captioned"):
            path = FINAL / f"{video}-final{suffix}.mp4"
            probe = json.loads(
                (lambda out: out[out.index("{") :])(
                    tool("ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                         str(path))))
            v = next(s for s in probe["streams"] if s["codec_type"] == "video")
            a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
            stills = None
            if suffix:
                stills = FINAL / "review-stills" / video
                stills.mkdir(exist_ok=True)
                for old in stills.glob("*.jpg"):
                    old.unlink()
            frames, black, frozen = inspect_picture(path, midpoints, stills)
            head = path.read_bytes()[:200000]
            entry = {
                "path": str(path), "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "seconds": float(probe["format"]["duration"]),
                "video": f'{v["codec_name"]} {v.get("profile")} {v["width"]}x{v["height"]} '
                         f'{v["r_frame_rate"]} {v["pix_fmt"]}',
                "decodedFrames": frames, "expectedFrames": script["frames"],
                "audio": f'{a["codec_name"]} {a["sample_rate"]} Hz {a["channels"]} ch',
                "videoSeconds": float(v["duration"]), "audioSeconds": float(a["duration"]),
                "blackRuns": black_runs(black), "unchangedOver8s": frozen,
                **audio_check(path, cues, asr if suffix else None),
            }
            entry["checks"] = {
                "1920x1080": (v["width"], v["height"]) == (1920, 1080),
                "30 fps": v["r_frame_rate"] == "30/1",
                "H.264 yuv420p": v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p",
                "AAC 48 kHz stereo": (a["codec_name"], a["sample_rate"], a["channels"])
                == ("aac", "48000", 2),
                "every frame decodes": frames == script["frames"],
                "stream durations match": abs(entry["videoSeconds"] - entry["audioSeconds"]) < 0.1,
                "duration in target": low <= entry["seconds"] <= high,
                "fast start": b"moov" in head,
                "loudness -16 to -14 LUFS": -16 <= entry["integratedLUFS"] <= -14,
                "true peak <= -1 dBTP": entry["truePeakDBTP"] <= -1.0,
                "no clipping": entry["clippedSamples"] == 0,
                # A short fade at the very start or end is intended.
                "no black stretch": all(n <= 20 or a_ + n >= frames - 20 for a_, n in entry["blackRuns"]),
            }
            clean = report["videos"].get(f"{video}-final.mp4")
            if suffix and clean:
                entry["checks"]["same audio and length as the clean export"] = (
                    entry["decodedAudioSha256"] == clean["decodedAudioSha256"]
                    and frames == clean["decodedFrames"])
                entry["checks"]["every narration part recognised"] = not entry["recognition"][
                    "narrationPartsUnderHalfRecognised"]
            report["videos"][path.name] = entry
            print(path.name, "FAILED:" if not all(entry["checks"].values()) else "passed",
                  [k for k, ok in entry["checks"].items() if not ok])
    for video in NAMES:
        phone_sheet(video)
    (FINAL / "reports/final-qa.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    good = report["privacy"]["passed"] and all(
        all(e["checks"].values()) for e in report["videos"].values())
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
