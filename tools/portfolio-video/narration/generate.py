"""Narration, timeline, captions and voice tracks from docs/portfolio-video/14_NARRATION_V2.md.

    .venv-tts/Scripts/python.exe narration/generate.py

Speech drives the timeline. Caption times come from the synthesiser's own word timestamps, so they
describe this audio; they are not estimated from a speaking rate.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import sys

from tts import APP, RATE, spoken, synthesize

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import butter, resample_poly, sosfilt  # noqa: E402

ROOT = APP.parents[1]
DOCS = ROOT / "docs/portfolio-video"
sys.path.insert(0, str(DOCS / "subtitles"))
from build import cues, stamp  # noqa: E402

VOICE, SPEED, FPS = "af_heart", 0.91, 30
LEAD, CARD_LEAD, GAP, TAIL = 0.35, 1.75, 0.22, 0.55
AUDIO = APP / "narration/audio"
# --scene 6.3 --scene A6 : synthesise these scenes again even though nothing changed.
FORCE = {sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--scene"}
OUTPUTS = {
    "showcase": ("showcase-v2", "showcase-final.en.srt"),
    "documentary": ("documentary", "documentary-final.en.srt"),
}
SEGMENT = re.compile(r"^#### (\S+) · (.+?) · (\d+(?:\.\d+)?) s\s*$")
ANCHOR = re.compile(r"^\(@([\d.]+)\) ")


def parse() -> dict[str, list[dict]]:
    videos: dict[str, list[dict]] = {}
    video = chapter = segment = None
    for line in (DOCS / "14_NARRATION_V2.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## video: "):
            video, chapter, segment = line.removeprefix("## video: ").strip(), None, None
            videos[video] = []
        elif line.startswith("### chapter "):
            number, title = line.removeprefix("### chapter ").split(" — ", 1)
            chapter = (int(number), title.strip())
        elif video and (match := SEGMENT.match(line)):
            segment = {"id": match[1], "title": match[2], "design": float(match[3]),
                       "chapter": chapter, "paragraphs": [""]}
            videos[video].append(segment)
        elif segment is not None and line.startswith(">"):
            words = line.lstrip(">").strip()
            if words:
                segment["paragraphs"][-1] = f"{segment['paragraphs'][-1]} {words}".strip()
            else:
                segment["paragraphs"].append("")
    return videos


def speech(video: str, name: str, text: str):
    """Synthesise one paragraph, reusing the stored original when nothing changed."""
    folder = AUDIO / "raw" / video
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(
        json.dumps([spoken(text), VOICE, SPEED], ensure_ascii=False).encode()
    ).hexdigest()[:16]
    wav, meta = folder / f"{name}.wav", folder / f"{name}.json"
    if wav.exists() and meta.exists():
        stored = json.loads(meta.read_text(encoding="utf-8"))
        if stored["key"] == key and name.split("-")[0] not in FORCE:
            return sf.read(wav, dtype="float32")[0], stored["words"]
    audio, words = synthesize(text, VOICE, SPEED)
    sf.write(wav, audio, RATE, subtype="PCM_24")
    meta.write_text(json.dumps({"key": key, "text": text, "words": words}, ensure_ascii=False),
                    encoding="utf-8")
    return audio, words


def trim(audio: np.ndarray, words: list) -> tuple[np.ndarray, list]:
    """Cut the silence around an utterance, keeping a short breath either side."""
    loud = np.flatnonzero(np.abs(audio) > 0.004)
    start = max(int(loud[0]) - int(0.04 * RATE), 0)
    end = min(int(loud[-1]) + int(0.12 * RATE), len(audio))
    shift = start / RATE
    return audio[start:end], [(w, max(a - shift, 0), max(b - shift, 0)) for w, a, b in words]


def norm(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def caption_times(text: str, words: list, seconds: float) -> list[tuple[str, float, float, bool]]:
    """(caption, start, end, matched) per block, from the spoken word timestamps."""
    blocks = cues([text])
    written = [norm(w) for block in blocks for w in block.split()]
    heard = [(norm(w), a, b) for w, a, b in words if norm(w)]
    matcher = difflib.SequenceMatcher(None, written, [h[0] for h in heard], autojunk=False)
    start_of: dict[int, float] = {}
    for i, j, size in matcher.get_matching_blocks():
        for k in range(size):
            start_of[i + k] = heard[j + k][1]
    out, index = [], 0
    starts = []
    for block in blocks:
        matched = index in start_of
        if index == 0:
            at = 0.0
        elif matched:
            at = start_of[index]
        else:
            # A respelt term opens this block: interpolate between the nearest matched words.
            before = max((k for k in start_of if k < index), default=0)
            after = min((k for k in start_of if k > index), default=len(written))
            a = start_of.get(before, 0.0)
            b = start_of.get(after, seconds)
            at = a + (b - a) * (index - before) / max(after - before, 1)
        starts.append((at, matched or index == 0))
        index += len(block.split())
    for n, block in enumerate(blocks):
        begin, matched = starts[n]
        finish = starts[n + 1][0] if n + 1 < len(blocks) else seconds
        out.append((block, begin, finish, matched))
    return out


def write_voice(track: np.ndarray, path) -> None:
    """48 kHz mono 24-bit. A high-pass and a level trim only: no heavy compression."""
    sos = butter(2, 70, "highpass", fs=RATE, output="sos")
    audio = resample_poly(sosfilt(sos, track), 2, 1)
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio * min(10 ** (-3 / 20) / peak, 4.0)
    sf.write(path, audio.astype("float32"), RATE * 2, subtype="PCM_24")


def build(video: str, segments: list[dict]) -> dict:
    name, srt_name = OUTPUTS[video]
    cursor = 0
    timeline, captions, placed, notes = [], [], [], []
    seen_chapter = None
    total_words = total_speech = estimated = 0
    for segment in segments:
        chapter = segment["chapter"]
        first = chapter is not None and chapter[0] != seen_chapter
        seen_chapter = chapter[0] if chapter else seen_chapter
        lead = CARD_LEAD if first and 1 < chapter[0] < 10 else LEAD
        parts = []
        for number, raw in enumerate(p for p in segment["paragraphs"] if p):
            match = ANCHOR.match(raw)
            text = ANCHOR.sub("", raw)
            audio, words = trim(*speech(video, f"{segment['id']}-{number + 1:02}", text))
            parts.append({"anchor": float(match[1]) if match else 0.0, "text": text,
                          "audio": audio, "words": words, "seconds": len(audio) / RATE,
                          "name": f"{segment['id']}-{number + 1:02}"})

        design = segment["design"]
        # Where speech ends well before the design length, close up the idle time (by 15% at most).
        needed = lead + sum(p["seconds"] + GAP for p in parts) + TAIL
        pace = min(1.0, max(0.85, needed / design))
        end = 0.0
        for n, part in enumerate(parts):
            earliest = lead if n == 0 else end + GAP
            part["at"] = max(earliest, part["anchor"] * pace)
            end = part["at"] + part["seconds"]
        seconds = max(design * pace, end + TAIL)
        frames = math.ceil(seconds * FPS)

        # Video frame -> design frame. Each anchored shot arrives just before its sentence.
        knots = [(0, 0)]
        for part in parts[1:]:
            video_frame = round((part["at"] - 0.2) * FPS)
            design_frame = round(part["anchor"] * FPS)
            if video_frame > knots[-1][0] and design_frame > knots[-1][1]:
                knots.append((video_frame, design_frame))
        knots.append((frames, round(design * FPS)))
        for (v0, d0), (v1, d1) in zip(knots, knots[1:]):
            speed = (d1 - d0) / (v1 - v0)
            if speed < 0.6 or speed > 1.4:
                notes.append(f"{segment['id']}: picture runs at {speed:.2f}x between frames "
                             f"{v0} and {v1}")

        for part in parts:
            at = cursor / FPS + part["at"]
            placed.append({
                "name": part["name"], "scene": segment["id"],
                "chapter": chapter[0] if chapter else 0,
                "at": round(at, 3), "seconds": round(part["seconds"], 3), "text": part["text"],
                "spoken": spoken(part["text"]),
                "audio": f"narration/audio/raw/{video}/{part['name']}.wav",
                "words": [[w, round(at + a, 3), round(at + b, 3)] for w, a, b in part["words"]],
            })
            sample = round(at * RATE)
            part["sample"] = sample
            for block, begin, finish, matched in caption_times(
                part["text"], part["words"], part["seconds"]
            ):
                captions.append({"start": round(at + begin, 3), "end": round(at + finish - 0.02, 3),
                                 "text": block})
                estimated += 0 if matched else 1
            total_words += len(part["text"].split())
            total_speech += part["seconds"]
        timeline.append({
            "id": segment["id"], "title": segment["title"],
            "chapter": chapter[0] if chapter else 0,
            "chapterTitle": chapter[1] if chapter else "",
            "from": cursor, "frames": frames, "design": round(design * FPS), "knots": knots,
            "_parts": parts,
        })
        cursor += frames

    # One continuous narration track, the exact length of the video.
    track = np.zeros(round(cursor / FPS * RATE), dtype="float32")
    for segment in timeline:
        for part in segment.pop("_parts"):
            start = part["sample"]
            track[start : start + len(part["audio"])] += part["audio"]
    overlaps = [
        (a["name"], b["name"]) for a, b in zip(placed, placed[1:])
        if b["at"] < a["at"] + a["seconds"] - 0.001
    ]
    assert not overlaps, f"narration overlaps: {overlaps}"
    assert all(a["end"] <= b["start"] + 0.001 for a, b in zip(captions, captions[1:]))
    assert captions[-1]["end"] <= cursor / FPS

    (APP / "public/audio").mkdir(parents=True, exist_ok=True)
    source = AUDIO / f"{video}-track-24k.wav"
    sf.write(source, track, RATE, subtype="PCM_24")
    voice = APP / f"public/audio/{video}-voice.wav"
    write_voice(track, voice)

    generated = APP / "src/data/generated" / f"{name}.json"
    generated.write_text(
        json.dumps({"frames": cursor, "segments": timeline, "captions": captions}, indent=2,
                   ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    srt = "\n".join(
        f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}\n"
        for i, c in enumerate(captions, 1)
    )
    (DOCS / "subtitles" / srt_name).write_text(srt, encoding="utf-8")
    final = ROOT / "output/video/final"
    final.mkdir(parents=True, exist_ok=True)
    (final / srt_name).write_text(srt, encoding="utf-8")
    (AUDIO / f"{video}-cues.json").write_text(
        json.dumps(placed, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "seconds": round(cursor / FPS, 1), "scenes": len(timeline), "audioFiles": len(placed),
        "captions": len(captions), "captionStartsInterpolated": estimated,
        "words": total_words, "speechSeconds": round(total_speech, 1),
        "wordsPerMinute": round(total_words / total_speech * 60), "pictureSpeedNotes": notes,
    }


def main() -> None:
    report = {"voice": VOICE, "speed": SPEED}
    for video, segments in parse().items():
        report[video] = build(video, segments)
    (AUDIO / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
