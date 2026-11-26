"""Three voice samples, each transcribed back by a local speech recogniser.

    .venv-tts/Scripts/python.exe narration/samples.py

This measures pace and whether technical words survive recognition. It cannot judge how pleasant
or natural a voice sounds; that needs a person to listen to narration/samples/*.wav.
"""

from __future__ import annotations

import difflib
import json
import pathlib
import re

from tts import APP, RATE, synthesize

import soundfile as sf  # noqa: E402

VOICES = ["am_michael", "af_heart", "bm_george"]
TEXT = (
    "This multi-tenant SaaS platform uses RAG with FastAPI, PostgreSQL and pgvector. "
    "Redis and Celery run background work, and Next.js serves the dashboard. "
    "Access uses RBAC and forced RLS. Answers stream over SSE, and providers require HTTPS. "
    "Successful responses had a P95 of one thousand six hundred and eighty-two milliseconds. "
    "The score moved from eighty and a half to eighty-five point seven five. "
    "Built with Codex and Claude Code. Portfolio: venuja.online."
)


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def main() -> None:
    from faster_whisper import WhisperModel

    asr = WhisperModel("small.en", device="cpu", compute_type="int8",
                       download_root=str(APP / ".cache-tts/whisper"))
    out = APP / "narration/samples"
    out.mkdir(exist_ok=True)
    report = {}
    for voice in VOICES:
        audio, timing = synthesize(TEXT, voice)
        path = out / f"{voice}.wav"
        sf.write(path, audio, RATE, subtype="PCM_24")
        heard = " ".join(s.text for s in asr.transcribe(str(path), beam_size=5)[0])
        match = difflib.SequenceMatcher(None, words(TEXT), words(heard)).ratio()
        seconds = len(audio) / RATE
        report[voice] = {
            "seconds": round(seconds, 2),
            "wordsPerMinute": round(len(TEXT.split()) / seconds * 60),
            "recognitionSimilarity": round(match, 3),
            "timedWords": len(timing),
            "heard": heard.strip(),
        }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
