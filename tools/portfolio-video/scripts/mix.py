"""Original music bed, interface sounds and the final stereo mix; then mux onto a silent picture.

    .venv-tts/Scripts/python.exe scripts/mix.py [--sample SECONDS]

Everything here is synthesised from sine waves and noise by this script: no samples, loops or
third-party recordings, and no recognisable melody. Narration comes from public/audio/*-voice.wav.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pyloudnorm
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

APP = pathlib.Path(__file__).resolve().parents[1]
SR = 48000
TARGET_LUFS, CEILING_DBTP = -15.0, -1.0
NAMES = {"showcase": "showcase-v2", "documentary": "documentary"}


def db(value: float) -> float:
    return 10 ** (value / 20)


def tone(freq: float, seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return np.sin(2 * np.pi * freq * t)


def music(seconds: float) -> np.ndarray:
    """A slow four-chord ambient pad with a soft pulse at 84 BPM. Original, stereo."""
    chords = [(110.0, 164.81, 220.0, 261.63), (87.31, 130.81, 220.0, 261.63),
              (98.0, 146.83, 196.0, 246.94), (82.41, 123.47, 196.0, 246.94)]
    bar = 4 * 60 / 84 * 2
    total = int(seconds * SR)
    out = np.zeros((total, 2))
    fade = int(1.6 * SR)
    for i in range(int(seconds / bar) + 1):
        start = int(i * bar * SR)
        length = int((bar + 1.6) * SR)
        envelope = np.ones(length)
        envelope[:fade] = np.sin(np.linspace(0, np.pi / 2, fade)) ** 2
        envelope[-fade:] = envelope[:fade][::-1]
        for channel, detune in enumerate((0.9985, 1.0015)):
            pad = sum(
                tone(f * detune, length / SR)[:length]
                + 0.25 * tone(f * 2 * detune, length / SR)[:length]
                for f in chords[i % 4]
            ) / 5
            end = min(start + length, total)
            if end > start:
                out[start:end, channel] += (pad * envelope)[: end - start]
    beat = 60 / 84
    pulse = tone(55.0, 0.28) * np.exp(-np.arange(int(0.28 * SR)) / (0.07 * SR))
    for n in range(int(seconds / beat)):
        start = int(n * beat * SR)
        end = min(start + len(pulse), total)
        out[start:end] += (0.35 if n % 2 == 0 else 0.18) * pulse[: end - start, None]
    out = sosfilt(butter(2, 1800, "lowpass", fs=SR, output="sos"), out, axis=0)
    ramp = int(2.5 * SR)
    out[:ramp] *= np.linspace(0, 1, ramp)[:, None]
    out[-ramp:] *= np.linspace(1, 0, ramp)[:, None]
    return out / np.max(np.abs(out))


def tick() -> np.ndarray:
    """A quiet, soft interface click."""
    length = int(0.09 * SR)
    t = np.arange(length) / SR
    wave = np.sin(2 * np.pi * 880 * t) * np.exp(-t / 0.018)
    wave[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return wave


def duck(voice: np.ndarray) -> np.ndarray:
    """Gain for the music: lower while speech is present, with gentle attack and release."""
    block = SR // 100
    blocks = len(voice) // block + 1
    padded = np.pad(voice, (0, blocks * block - len(voice)))
    active = np.sqrt((padded.reshape(blocks, block) ** 2).mean(axis=1)) > db(-45)
    # Hold across the short gaps inside a sentence, and open early.
    hold = np.convolve(active.astype(float), np.ones(60), mode="same") > 0
    gain = np.empty(blocks)
    level = 1.0
    for i, speaking in enumerate(hold):
        target = db(-9) if speaking else 1.0
        level += (target - level) * (0.12 if target < level else 0.025)
        gain[i] = level
    return np.interp(np.arange(len(voice)), np.arange(blocks) * block, gain)


def true_peak(audio: np.ndarray) -> float:
    return float(20 * np.log10(np.max(np.abs(resample_poly(audio, 4, 1, axis=0))) + 1e-12))


def mix(video: str, limit: float | None = None) -> dict:
    script = json.loads(
        (APP / "src/data/generated" / f"{NAMES[video]}.json").read_text(encoding="utf-8"))
    seconds = script["frames"] / 30
    voice, rate = sf.read(APP / f"public/audio/{video}-voice.wav")
    assert rate == SR
    total = round(seconds * SR)
    voice = np.pad(voice, (0, max(total - len(voice), 0)))[:total]

    meter = pyloudnorm.Meter(SR)
    voice_stereo = np.column_stack([voice, voice])
    voice_stereo *= db(-16 - meter.integrated_loudness(voice_stereo))
    bed = music(seconds)[:total]
    # The bed sits about 17 dB under the voice between sentences and 26 dB under during them.
    bed *= db(-33 - meter.integrated_loudness(bed))
    bed *= duck(voice)[:, None]
    effects = np.zeros((total, 2))
    click = tick() * db(-30)
    chapters = {}
    for segment in script["segments"]:
        chapters.setdefault(segment["chapter"] or segment["id"], segment["from"])
    for frame in chapters.values():
        start = round(frame / 30 * SR)
        end = min(start + len(click), total)
        if start:
            effects[start:end] += click[: end - start, None]

    stereo = voice_stereo + bed + effects
    for _ in range(3):
        stereo *= db(TARGET_LUFS - meter.integrated_loudness(stereo))
        # Soft ceiling for the few peaks above it.
        ceiling = db(CEILING_DBTP - 0.6)
        knee = ceiling * 0.8
        over = np.abs(stereo) > knee
        stereo[over] = np.sign(stereo[over]) * (
            knee + (ceiling - knee) * np.tanh((np.abs(stereo[over]) - knee) / (ceiling - knee)))
    if limit:
        stereo = stereo[: int(limit * SR)]
    path = APP / f"narration/audio/{video}-mix.wav"
    sf.write(path, stereo, SR, subtype="PCM_24")
    sf.write(APP / f"narration/audio/{video}-music.wav", bed, SR, subtype="PCM_24")
    return {
        "file": str(path.relative_to(APP)), "seconds": round(len(stereo) / SR, 3),
        "integratedLUFS": round(meter.integrated_loudness(stereo), 2),
        "truePeakDBTP": round(true_peak(stereo), 2),
        "samplePeakDBFS": round(float(20 * np.log10(np.abs(stereo).max())), 2),
    }


def main() -> None:
    limit = float(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else None
    report = {video: mix(video, limit) for video in NAMES}
    (APP / "narration/audio/mix-report.json").write_text(json.dumps(report, indent=2),
                                                         encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
