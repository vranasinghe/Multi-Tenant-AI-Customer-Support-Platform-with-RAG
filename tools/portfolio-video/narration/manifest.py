"""One record per scene, joined from what the generator produced.

    .venv-tts/Scripts/python.exe narration/manifest.py      writes narration/manifest.json

Narration, timing, audio and captions come from 14_NARRATION_V2.md through generate.py. The footage
and claim references below are maintained by hand against the scene components and the fact check.
"""

from __future__ import annotations

import json
import re

from tts import APP

SCENE_FILES = [
    "src/scenes/showcase-v2/scenes.tsx",
    "src/scenes/documentary/intro.tsx",
    "src/scenes/documentary/demo.tsx",
    "src/scenes/documentary/architecture.tsx",
    "src/scenes/documentary/security.tsx",
    "src/scenes/documentary/challenges.tsx",
    "src/scenes/documentary/method.tsx",
    "src/scenes/documentary/closing.tsx",
]
FOOTAGE = {
    "A2": ["R15", "R03", "R05", "R09", "R12"], "A3": ["R04", "R07", "R14", "R09", "R13", "R10"],
    "1a": ["R15", "R05", "R09", "R12"],
    "2a": ["R01", "R02", "R03", "R04", "R05", "R06"], "2b": ["R07"],
    "2c": ["R08 (sanitized)", "R09", "R12", "R13"],
    "5a": ["R14"], "6.8": ["R12"], "6.9": ["R10"], "10a": ["R15", "R09", "R12"],
}
# Claim ids from docs/portfolio-video/00_PROJECT_FACT_CHECK.md.
CLAIMS = {
    "A3": ["F-05", "F-08", "F-09", "F-42", "F-55"], "A4": ["F-20", "F-21"],
    "A5": ["F-64", "F-68", "F-69", "F-70"],
    "2a": ["F-01", "F-03", "F-04", "F-05", "F-06", "F-07"], "2b": ["F-08", "F-34", "X5"],
    "2c": ["F-09", "F-10", "F-11", "X10"],
    "3a": ["F-20", "F-21"], "3b": ["F-24", "F-40"], "3c": ["F-22", "F-23", "F-25"],
    "3d": ["F-12"], "3e": ["F-20", "F-21"],
    "4a": ["F-30", "F-31", "F-32"], "4b": ["F-33", "F-35", "F-36"], "4c": ["F-37", "F-38"],
    "5a": ["F-42"], "5b": ["F-40", "F-41", "F-43"], "5c": ["F-44"],
    "6.1": ["F-50"], "6.2": ["F-52"], "6.3": ["AUD-03 report"], "6.4": ["AUD-04 report"],
    "6.5": ["F-53"], "6.6": ["AUD-05 report"], "6.7": ["F-54"], "6.8": ["AUD-06 report"],
    "6.9": ["F-55", "F-56"], "6.10": ["validation results", "DEVBEAT-CRASH"], "6.11": ["F-66"],
    "7b": ["F-60", "F-61", "F-62", "F-63", "F-64", "F-69", "F-70"], "7c": ["F-67"],
    "7d": ["F-65", "capacity-100.json"], "7e": ["F-68", "section 6"],
    "8a": ["section 9"], "9a": ["section 6"],
}


def main() -> None:
    used = set()
    for name in SCENE_FILES:
        used |= set(re.findall(r'"(R\d\d)-', (APP / name).read_text(encoding="utf-8")))
    listed = {clip[:3] for clips in FOOTAGE.values() for clip in clips}
    assert used == listed, f"footage table out of date: {used ^ listed}"

    manifest = {}
    for video, data in (("showcase", "showcase-v2"), ("documentary", "documentary")):
        script = json.loads((APP / f"src/data/generated/{data}.json").read_text(encoding="utf-8"))
        cues = json.loads((APP / f"narration/audio/{video}-cues.json").read_text(encoding="utf-8"))
        scenes = []
        for s in script["segments"]:
            parts = [c for c in cues if c["scene"] == s["id"]]
            assert parts, f"{s['id']} has no narration"
            for part in parts:
                assert (APP / part["audio"]).stat().st_size > 1000, part["audio"]
            start, end = s["from"] / 30, (s["from"] + s["frames"]) / 30
            scenes.append({
                "scene": s["id"], "chapter": s["chapter"], "title": s["title"],
                "startSeconds": round(start, 3), "frames": s["frames"],
                "narration": parts,
                "audioSeconds": round(sum(p["seconds"] for p in parts), 3),
                "footage": FOOTAGE.get(s["id"], []),
                "captions": [c for c in script["captions"] if start <= c["start"] < end],
                "claims": CLAIMS.get(s["id"], []),
            })
        manifest[video] = scenes
        print(video, len(scenes), "scenes,", len(cues), "narration files, all present")
    (APP / "narration/manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
