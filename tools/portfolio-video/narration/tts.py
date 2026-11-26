"""Shared local text-to-speech: Kokoro-82M on CPU, nothing leaves this machine after the model
download. Run with .venv-tts/Scripts/python.exe.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(APP / ".cache-tts/hf"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import numpy as np  # noqa: E402

RATE = 24000  # Kokoro output
REPO = "hexgrad/Kokoro-82M"

# The pronunciation dictionary is data: narration/pronunciation.json.
PRONUNCIATION = json.loads(
    (pathlib.Path(__file__).with_name("pronunciation.json")).read_text(encoding="utf-8")
)
LEXICON: dict[str, str] = PRONUNCIATION["terms"]


def spoken(text: str) -> str:
    """The speech-normalised form of display text."""
    # Longest first, in one pass, so a replacement is never replaced again.
    keys = sorted(LEXICON, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w.])(" + "|".join(map(re.escape, keys)) + r")(?![\w])")

    def swap(match: re.Match[str]) -> str:
        value = LEXICON[match[1]]
        return f"[{match[1]}]({value})" if value.startswith("/") else value

    return pattern.sub(swap, text)


_pipelines: dict[str, object] = {}

def pipeline(voice: str):
    from kokoro import KPipeline

    lang = voice[0]  # "a" American, "b" British
    if lang not in _pipelines:
        _pipelines[lang] = KPipeline(lang_code=lang, repo_id=REPO, device="cpu")
    return _pipelines[lang]

def synthesize(text: str, voice: str, speed: float = 1.0):
    """Return (samples at 24 kHz, [(word, start_s, end_s)]) from the synthesiser's own timing."""
    audio, words, offset = [], [], 0.0
    for result in pipeline(voice)(spoken(text), voice=voice, speed=speed):
        chunk = result.audio.numpy()
        for token in result.tokens or []:
            if token.start_ts is not None and token.end_ts is not None:
                words.append((token.text, offset + token.start_ts, offset + token.end_ts))
        audio.append(chunk)
        offset += len(chunk) / RATE
    return np.concatenate(audio), words
