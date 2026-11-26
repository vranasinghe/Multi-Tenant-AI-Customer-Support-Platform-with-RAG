"""Build the voice-over script and draft subtitles from the two video scripts.

    python docs/portfolio-video/subtitles/build.py

The narration blocks in 02 and 03 are the only source. Timings are drafts spread by word count
inside each scene: re-time them against the recorded voice.
"""

from __future__ import annotations

import pathlib
import re
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]
VIDEOS = [
    ("Video A — showcase", "02_CINEMATIC_TRAILER_SCRIPT.md", "video-a-showcase.en.srt", 80),
    ("Video B — documentary", "03_FULL_DOCUMENTARY_SCRIPT.md", "video-b-documentary.en.srt", 600),
]
HEADING = re.compile(
    r"^## Scene (\S+) — (.+?) \((\d+):(\d\d)–(\d+):(\d\d), (\d+) s\)\s*$", re.MULTILINE
)
NARRATION = re.compile(r"^\*\*Narration\*\*\n((?:^>.*\n)+)", re.MULTILINE)
LINE = 42  # characters per subtitle line
LEAD, TAIL = 0.4, 0.4  # silence kept at each end of a scene


def scenes(path: pathlib.Path):
    source = path.read_text(encoding="utf-8")
    found = list(HEADING.finditer(source))
    for i, match in enumerate(found):
        body = source[match.end() : found[i + 1].start() if i + 1 < len(found) else None]
        block = NARRATION.search(body)
        if not block:
            raise SystemExit(f"{path.name}: scene {match[1]} has no narration")
        paragraphs, current = [], []
        for line in block[1].splitlines():
            words = line.lstrip(">").strip()
            if words:
                current.append(words)
            elif current:
                paragraphs.append(" ".join(current))
                current = []
        if current:
            paragraphs.append(" ".join(current))
        start = int(match[3]) * 60 + int(match[4])
        end = int(match[5]) * 60 + int(match[6])
        if end - start != int(match[7]):
            raise SystemExit(f"{path.name}: scene {match[1]} duration does not match its times")
        yield match[1], match[2], start, end, paragraphs


def cues(paragraphs: list[str]) -> list[str]:
    """Split at sentence and clause ends into blocks of at most two lines."""
    out: list[str] = []
    for paragraph in paragraphs:
        for sentence in re.split(r"(?<=[.?!:])\s+", paragraph):
            wrapped = textwrap.wrap(sentence, LINE)
            if len(wrapped) <= 2:
                out.append("\n".join(wrapped))
                continue
            chunk = ""
            for part in re.split(r"(?<=,)\s+", sentence):
                trial = f"{chunk} {part}".strip()
                if len(textwrap.wrap(trial, LINE)) <= 2:
                    chunk = trial
                    continue
                if chunk:
                    out.append("\n".join(textwrap.wrap(chunk, LINE)))
                lines = textwrap.wrap(part, LINE)
                while len(lines) > 2:
                    out.append("\n".join(lines[:2]))
                    lines = lines[2:]
                chunk = " ".join(lines)
            if chunk:
                out.append("\n".join(textwrap.wrap(chunk, LINE)))
    return out


def stamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main() -> int:
    script = [
        "# Voice-over script (superseded)",
        "",
        "**Superseded** for the revised videos by [16_VOICEOVER_SCRIPT.md](16_VOICEOVER_SCRIPT.md).",
        "This copy matches the original 80-second preview only.",
        "",
        "Generated from the video scripts by `subtitles/build.py`. **Do not edit here.**",
        "",
        "How to read it: quiet room, 15–20 cm from the microphone, one scene per take, a second of",
        "silence before and after. Target 120–145 words per minute; pause at blank lines. The",
        "rate below counts written words: spoken numbers run longer, so check scene 09 aloud.",
        "",
        "Say: *pgvector* “P-G vector” · *FastAPI* “fast A-P-I” · *Celery* “SELL-uh-ree” ·",
        "*Redis* “RED-iss” · *RBAC* “R-back” · *venuja.online* “venuja dot online”.",
    ]
    problems = []
    for title, source, subtitle, length in VIDEOS:
        script += ["", f"## {title}"]
        srt, number, cursor, total_words = [], 0, 0, 0
        for scene, name, start, end, paragraphs in scenes(ROOT / source):
            if start != cursor:
                problems.append(f"{source}: scene {scene} starts at {start}s, expected {cursor}s")
            cursor = end
            words = sum(len(p.split()) for p in paragraphs)
            total_words += words
            rate = words / (end - start) * 60
            if not 105 <= rate <= 145:
                problems.append(f"{source}: scene {scene} is {rate:.0f} words per minute")
            script += [
                "",
                f"### {scene} · {name} · {start // 60}:{start % 60:02} · {end - start} s · "
                f"{words} words · {rate:.0f} wpm",
            ]
            for paragraph in paragraphs:
                script += ["", paragraph]
            blocks = cues(paragraphs)
            weights = [len(b.split()) + 2 for b in blocks]
            span = end - start - LEAD - TAIL
            at = start + LEAD
            for block, weight in zip(blocks, weights, strict=True):
                until = at + span * weight / sum(weights)
                number += 1
                srt.append(f"{number}\n{stamp(at)} --> {stamp(until - 0.05)}\n{block}\n")
                at = until
        if cursor != length:
            problems.append(f"{source}: ends at {cursor}s, expected {length}s")
        script += ["", f"*{total_words} words over {length} s.*"]
        (ROOT / "subtitles" / subtitle).write_text("\n".join(srt), encoding="utf-8")
        print(f"{subtitle}: {number} cues, {total_words} words, {length}s")
    (ROOT / "07_VOICEOVER_SCRIPT.md").write_text("\n".join(script) + "\n", encoding="utf-8")
    for problem in problems:
        print("CHECK:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
