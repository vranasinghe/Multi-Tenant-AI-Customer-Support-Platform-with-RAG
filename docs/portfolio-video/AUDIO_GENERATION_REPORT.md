# Audio generation report

**The narration is AI-generated. It is not the developer's voice, and no voice was cloned.**

## Engine

Kokoro-82M (`hexgrad/Kokoro-82M`, Apache-2.0) through the official `kokoro` 0.9.4 package, on CPU,
in an isolated Python 3.11 environment (`tools/portfolio-video/.venv-tts`). No script or source was
sent to an external service. Piper was not needed.

## Voice choice

Three stock voices read the same technical paragraph and a local recogniser (Whisper `small.en`)
transcribed each. Results: `tools/portfolio-video/narration/samples/report.json`.

| Voice | Model-card grade | Pace in sample (speed 1.0) | Recognition similarity |
|---|---|---|---|
| `af_heart` (American) | **A** | 123 wpm | 0.72 |
| `am_michael` (American) | C+ | 113 wpm | 0.71 |
| `bm_george` (British) | C | 124 wpm | 0.74 |

**Chosen: `af_heart`**, for the highest published quality grade, a pace near the target and clean
recognition of the technical terms. The similarity scores are close and held down by number
formatting ("85.75" against spoken words), so they did not decide it.

**Limitation: I cannot hear audio.** Naturalness, tone and whether a pronunciation sounds right
have not been judged by anyone. Listen to the three files in `narration/samples/` and to the final
videos.

## Synthesis settings

| | Showcase | Documentary |
|---|---|---|
| Speed | 0.91 | 0.91 |
| Narration parts | 22 | 113 |
| Words | 208 | about 1,650 |
| Speaking pace | 140 wpm | 143 wpm |
| Video length | 100.2 s | 773.7 s (12:54) |

The target was 125–140 words per minute; the documentary is about 3 above it. Slower would have
taken it past 13 minutes.

## Pronunciation

Handled in `narration/tts.py` (spoken form only; captions keep the written term): RAG, SaaS,
FastAPI, Next.js, PostgreSQL, pgvector, Redis, Celery, RBAC, RLS, SSE, HTTPS, HttpOnly, P95, Codex,
venuja. Claude is left to the model's own dictionary after an override sounded wrong to the
recogniser. Figures are written as words in the narration.

**Please listen to:** "venuja" (my phoneme spelling is a guess at how you say it), "Celery",
"pgvector", "PostgreSQL".

## Processing and files

| Step | Detail |
|---|---|
| Originals | One 24 kHz 24-bit WAV per narration part, with word timestamps: `narration/audio/raw/` |
| Voice tracks | `public/audio/showcase-voice.wav`, `documentary-voice.wav`: 48 kHz, mono, 24-bit; 70 Hz high-pass and level trim, no heavy compression |
| Music | Original ambient pad and soft pulse, ducked 9 dB under speech |
| Effects | A quiet tick at chapter starts only |
| Mix | Stereo, −15 LUFS integrated, soft ceiling below −1 dBTP: `scripts/mix.py` |

## Timing

Scene lengths come from the measured audio. Caption times come from the synthesiser's own word
timestamps (2 documentary caption starts are interpolated because the block opens on a respelt
term). The delivered audio is then checked independently by speech recognition; see
[FINAL_VIDEO_QA_REPORT.md](FINAL_VIDEO_QA_REPORT.md).

## To change the narration

Edit [14_NARRATION_V2.md](14_NARRATION_V2.md), then from `tools/portfolio-video`:

```powershell
.venv-tts/Scripts/python.exe narration/generate.py
```

```powershell
.venv-tts/Scripts/python.exe scripts/mix.py
```

```powershell
node scripts/render.mjs documentary
```
