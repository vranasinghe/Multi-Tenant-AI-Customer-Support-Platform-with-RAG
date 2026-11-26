"""Audition how the narrator would say the portfolio domain.

    .venv-tts/Scripts/python.exe narration/domain_sample.py

The spelling comes from pronunciation.json ("domain"). The videos do not say the domain; this
sample is for the owner to approve or correct it first. The visible URL is never changed.
"""

from __future__ import annotations

from generate import SPEED, VOICE
from tts import APP, PRONUNCIATION, RATE, synthesize

import soundfile as sf  # noqa: E402


def main() -> None:
    out = APP / "public/audio/samples"
    out.mkdir(parents=True, exist_ok=True)
    text = f"Explore the full case study at {PRONUNCIATION['domain']}."
    audio, _ = synthesize(text, VOICE, SPEED)
    sf.write(out / "domain-venuja-online.wav", audio, RATE, subtype="PCM_24")
    print(out / "domain-venuja-online.wav", f"{len(audio) / RATE:.1f} s")


if __name__ == "__main__":
    main()
