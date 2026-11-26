"""Build Phase 3 timings, subtitle drafts and the recording guide from 14_NARRATION_V2.md.

    python docs/portfolio-video/subtitles/build_v2.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys

from build import LEAD, TAIL, cues, stamp

ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATED = ROOT.parents[1] / "tools/portfolio-video/src/data/generated"
FPS = 30
RATE = 141  # words per minute for scenes timed from their text
MARK = re.compile(r"^\(at ([\d.]+) s\) ")
SEGMENT = re.compile(r"^#### (\S+) · (.+?)(?: · (min )?(\d+) s)?\s*$")
OUTPUTS = {
    "showcase": ("showcase-v2", "video-a-showcase-v2.en.srt", (80, 90)),
    "documentary": ("documentary", "video-b-documentary-v2.en.srt", (480, 720)),
}


# Delivery notes per scene: words to stress, and phrases to pause after. They do not change the
# narration; the build fails if a phrase is no longer in the text.
DIRECTION = {
    "A1": (["strictly apart"], ["own knowledge,"]),
    "A2": (["multi-tenant"], ["support platform."]),
    "A3": (["fixed demo sentence", "cannot open"], ["carry their sources.", "this workspace."]),
    "A4": (["modular monolith"], ["retrieval intelligence."]),
    "A5": (["All seven now pass locally", "still unproven"], ["seven problems."]),
    "A6": (["venuja dot online"], ["applied AI."]),
    "1a": (["isolated"], ["data isolated?"]),
    "1b": (["only that one"], ["each time."]),
    "2a": (["fictional data", "refuses"], ["fictional data."]),
    "2b": (["not an AI answer", "retrieval"], ["important note:"]),
    "2c": (["synthetic demonstration data"], ["marks it resolved,"]),
    "3a": (["modular monolith"], ["four layers."]),
    "3b": (["role"], ["ordinary requests."]),
    "3c": (["Private object storage"], ["with pgvector."]),
    "3d": (["not separate services"], ["embedding models."]),
    "3e": (["do not make this microservices"], ["Docker containers."]),
    "4a": (["never cross a heading"], ["writing from it."]),
    "4b": (["Only sources that actually entered the prompt"], ["are merged."]),
    "4c": (["not that it supports the sentence", "untested"], ["to the model,"]),
    "5a": (["organization not found"], ["address,"]),
    "5b": (["forced row-level security"], ["enforce this."]),
    "5c": (["not a security certification"], ["listed proxies,"]),
    "6.0": (["had missed"], ["had missed."]),
    "6.1": (["none failed"], ["asking for another."]),
    "6.2": (["still unverified"], ["what was shown."]),
    "6.3": (["No real provider endpoint"], ["unencrypted."]),
    "6.4": (["remains unverified"], ["rate limits."]),
    "6.5": (["not yet a security sandbox"], ["memory limits."]),
    "6.6": (["seventeen minutes"], ["change nothing."]),
    "6.7": (["new object key"], ["stored pages."]),
    "6.8": (["silently"], ["stale data."]),
    "6.9": (["Chrome only"], ["usage fields."]),
    "6.10": (["still unexplained"], ["check scheduling."]),
    "6.11": (["only counts once restored", "not covered"], ["once restored."]),
    "7a": (["audit driven"], ["audit driven."]),
    "7b": (["pass locally", "fifteen hundred and five"], ["seven findings."]),
    "7c": (["each break was caught"], ["not clean."]),
    "7d": (["not real model or server performance"], ["failed unexpectedly."]),
    "7e": (["not independent certification"], ["point seven five."]),
    "8a": (["AI coding assistants", "process"], ["by hand."]),
    "9a": (["not existing features"], ["findings pass."]),
    "10a": (["venuja dot online"], ["AI engineering."]),
}
# Scenes whose first-person statements are the author's to confirm before recording.
CONFIRM = {"8a"}


def directed(identifier: str, paragraphs: list[str]) -> list[str]:
    stress, pauses = DIRECTION[identifier]
    text = "\n".join(paragraphs)
    # Positions are found in the untouched text, then markers are inserted from the end.
    inserts: list[tuple[int, str]] = []
    for phrases, before, after in ((stress, "**", "**"), (pauses, "", " ⏸")):
        for phrase in phrases:
            match = re.search(r"\s+".join(map(re.escape, phrase.split())), text)
            assert match, f"{identifier}: phrase not found: {phrase}"
            if before:
                inserts.append((match.start(), before))
            inserts.append((match.end(), after))
    for position, marker in sorted(inserts, key=lambda item: item[0], reverse=True):
        text = text[:position] + marker + text[position:]
    marked = text.split("\n")
    if identifier in CONFIRM:
        marked = [
            " ".join(f"**[CONFIRM]** {x}" for x in re.split(r"(?<=[.?!⏸])\s+(?!⏸)", p)) for p in marked
        ]
    return marked


def parse() -> dict[str, list[dict]]:
    videos: dict[str, list[dict]] = {}
    video, chapter, segment = None, None, None
    for line in (ROOT / "14_NARRATION_V2.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## video: "):
            video, chapter, segment = line.removeprefix("## video: ").strip(), None, None
            videos[video] = []
        elif line.startswith("### chapter "):
            number, title = line.removeprefix("### chapter ").split(" — ", 1)
            chapter = {"number": int(number), "title": title.strip()}
        elif video and (match := SEGMENT.match(line)):
            segment = {
                "id": match[1],
                "title": match[2],
                "chapter": chapter,
                "floor": int(match[4]) if match[4] and match[3] else 0,
                "fixed": int(match[4]) if match[4] and not match[3] else 0,
                "paragraphs": [""],
            }
            videos[video].append(segment)
        elif segment is not None and line.startswith(">"):
            words = line.lstrip(">").strip()
            if words:
                segment["paragraphs"][-1] = f"{segment['paragraphs'][-1]} {words}".strip()
            else:
                segment["paragraphs"].append("")
    return videos


def main() -> int:
    GENERATED.mkdir(parents=True, exist_ok=True)
    guide = [
        "# Voice-over recording guide",
        "",
        "Generated from [14_NARRATION_V2.md](14_NARRATION_V2.md). **Do not edit here.**",
        "",
        "## Before you record",
        "",
        "- Quiet room, 15–20 cm from the microphone, pop filter or slightly off-axis.",
        "- WAV, 48 kHz, 24-bit, mono. Peaks around −6 dB.",
        "- One take per scene, one second of silence before and after. Name takes by scene id.",
        "- Join the takes so each scene starts at its time below, then export one file per video:",
        "  `tools/portfolio-video/public/audio/showcase-voice.wav` and `documentary-voice.wav`.",
        "- If a take runs long, do not rush: tell the editor, the scene length can change.",
        "",
        "## Recording steps",
        "",
        "1. Approve or reword the **[CONFIRM]** statements in scene 8a.",
        "2. Record from [16_VOICEOVER_SCRIPT.md](16_VOICEOVER_SCRIPT.md): stress, pauses and",
        "   per-scene speaking times are marked there.",
        "3. In an audio editor (Audacity is free), place each take at its scene start time, plus any",
        "   *(+N s)* offset, with silence between.",
        "4. Export WAV, 48 kHz, 24-bit, mono, the full length of the video, to:",
        "   - `tools/portfolio-video/public/audio/showcase-voice.wav` (1:30)",
        "   - `tools/portfolio-video/public/audio/documentary-voice.wav` (11:37)",
        "5. Do not run a final render yet. Send both files for timing review: subtitles are then",
        "   re-timed to your voice. **Audio synchronization has not been checked.**",
        "",
        "## Pacing",
        "",
        "Aim for 125–140 words per minute: steady, a full stop is a breath. Pause one beat before a",
        "number and after a limitation. The rates below count written words; spoken numbers run",
        "longer, so rehearse scenes with figures.",
        "",
        "## Pronunciation",
        "",
        "| Term | Say |",
        "|---|---|",
        "| FastAPI | “fast A-P-I” |",
        "| pgvector | “P-G vector” |",
        "| PostgreSQL | “post-gres Q-L” |",
        "| Celery | “SELL-uh-ree” |",
        "| Redis | “RED-iss” |",
        "| RBAC | “R-back” |",
        "| SSE | “server-sent events” |",
        "| P95 | “ninety-fifth percentile” |",
        "| Codex, Claude | “CO-dex”, “klawd” |",
        "| HTTP, HTTPS | letter by letter |",
        "| venuja.online | “venuja dot online” |",
        "| 1,209 | “twelve hundred and nine” |",
        "| 1,505 | “fifteen hundred and five” |",
        "| 5,248 | “five thousand two hundred and forty-eight” |",
        "| 80.5 → 85.75 | “eighty and a half … eighty-five point seven five” |",
        "",
        "Chapter 8 contains first-person statements. **Confirm them, or reword, before recording**",
        "([fact check §9](00_PROJECT_FACT_CHECK.md)).",
    ]
    script = [
        "# Voice-over script (recording copy)",
        "",
        "Generated from [14_NARRATION_V2.md](14_NARRATION_V2.md). **Do not edit here.** Setup and",
        "file placement: [recording guide](15_VOICEOVER_GUIDE.md).",
        "",
        "**Bold** = stress. ⏸ = pause one beat (about half a second). *(+N s)* = begin that line N",
        "seconds after the scene starts, to match the picture. **[CONFIRM]** = a statement about you",
        "that is not yet confirmed; approve or reword it before recording.",
        "",
        "Scene lengths were sized for about 140 words per minute, which leaves little room for",
        "pauses. **Read at your natural pace.** Do not rush: scene lengths will be changed to fit",
        "your recording.",
    ]
    problems = []
    for video, segments in parse().items():
        name, subtitle, (low, high) = OUTPUTS[video]
        cursor, srt, captions, timeline, number = 0, [], [], [], 0
        guide += ["", f"## {'Showcase' if video == 'showcase' else 'Documentary'}"]
        chapter_seen = None
        script += ["", f"## {'Showcase' if video == 'showcase' else 'Documentary'}"]
        speaking, script_chapter = 0.0, None
        for segment in segments:
            raw = [p for p in segment["paragraphs"] if p]
            marks = [float(m[1]) if (m := MARK.match(p)) else None for p in raw]
            paragraphs = [MARK.sub("", p) for p in raw]
            words = sum(len(p.split()) for p in paragraphs)
            seconds = segment["fixed"] or max(math.ceil(words * 60 / RATE) + 1, segment["floor"])
            rate = words / seconds * 60
            if rate > 145 or (segment["fixed"] and rate < 105):
                problems.append(f"{video} {segment['id']}: {rate:.0f} words per minute")
            chapter = segment["chapter"]
            if chapter and chapter["number"] != chapter_seen:
                chapter_seen = chapter["number"]
                guide += ["", f"### Chapter {chapter['number']} — {chapter['title']}"]
            clock = f"{cursor // 60}:{cursor % 60:02}"
            spoken = words / 130 * 60
            speaking += spoken
            if chapter and chapter["number"] != script_chapter:
                script_chapter = chapter["number"]
                script += ["", f"### Chapter {chapter['number']} — {chapter['title']}"]
            script += ["", f"#### {segment['id']} · {segment['title']}", "",
                       f"Starts {clock} · scene {seconds} s · about {spoken:.0f} s of speech at 130 wpm "
                       f"· fits the scene at about {rate:.0f} wpm"]
            for mark, p in zip(marks, directed(segment["id"], paragraphs), strict=True):
                script += ["", f"*(+{mark:g} s)* {p}" if mark is not None else p]
            guide += ["", f"**{segment['id']} · {segment['title']}** — starts {clock} · "
                      f"{seconds} s · {words} words · {rate:.0f} wpm", ""]
            guide += [
                line
                for mark, p in zip(marks, paragraphs, strict=True)
                for line in (f"*(+{mark:g} s)* {p}" if mark is not None else p, "")
            ][:-1]
            # Silent-preview timing. A marked paragraph starts at its offset (matching a shot) and
            # ends before the next mark; unmarked scenes spread over the time the words need.
            if marks and marks[0] is not None:
                starts = [cursor + m for m in marks] + [cursor + seconds]
                groups = [
                    ([p], starts[i] + 0.2,
                     min(starts[i + 1], starts[i] + 1.2 + len(p.split()) * 60 / 120))
                    for i, p in enumerate(paragraphs)
                ]
            else:
                span = min(seconds - LEAD - TAIL, max(words * 60 / 128, 2))
                groups = [(paragraphs, cursor + LEAD, cursor + LEAD + span)]
            for group, begin, finish in groups:
                blocks = cues(group)
                weights = [len(b.split()) + 2 for b in blocks]
                at = begin
                for block, weight in zip(blocks, weights, strict=True):
                    until = at + (finish - begin) * weight / sum(weights)
                    number += 1
                    srt.append(f"{number}\n{stamp(at)} --> {stamp(until - 0.05)}\n{block}\n")
                    captions.append(
                        {"start": round(at, 3), "end": round(until - 0.05, 3), "text": block}
                    )
                    at = until
            timeline.append({
                "id": segment["id"], "title": segment["title"],
                "chapter": chapter["number"] if chapter else 0,
                "chapterTitle": chapter["title"] if chapter else "",
                "from": cursor * FPS, "frames": seconds * FPS,
            })
            cursor += seconds
        if not low <= cursor <= high:
            problems.append(f"{video}: {cursor} s is outside {low}–{high} s")
        (ROOT / "subtitles" / subtitle).write_text("\n".join(srt), encoding="utf-8")
        (GENERATED / f"{name}.json").write_text(
            json.dumps({"frames": cursor * FPS, "segments": timeline, "captions": captions}, indent=2,
                       ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n",
        )
        total = (f"*Total {cursor // 60}:{cursor % 60:02}; about {speaking / 60:.1f} minutes of "
                 "speech at 130 words per minute.*")
        guide += ["", total]
        script += ["", total]
        print(f"{video}: {len(timeline)} scenes, {cursor} s, {number} cues")
    (ROOT / "16_VOICEOVER_SCRIPT.md").write_text("\n".join(script) + "\n", encoding="utf-8")
    (ROOT / "15_VOICEOVER_GUIDE.md").write_text("\n".join(guide) + "\n", encoding="utf-8")
    for problem in problems:
        print("CHECK:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
