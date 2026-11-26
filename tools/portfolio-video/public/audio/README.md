# Audio inputs

Nothing here is generated. Add your own files; they stay out of Git.

| File | Track | Used when |
|---|---|---|
| `showcase-voice.wav` | Narration, showcase | present |
| `documentary-voice.wav` | Narration, documentary | present |
| `showcase-music.wav`, `documentary-music.wav` | Background music | only if the matching `.licence.txt` is also present |
| `showcase-music.licence.txt`, `documentary-music.licence.txt` | The licence or terms for that track (YouTube and your website) | |
| `click.wav` | Interface sound at the scene cues | present |

With no voice file for a video, its renders are marked **silent preview** and a final render is
refused.

Record from [15_VOICEOVER_GUIDE.md](../../../../docs/portfolio-video/15_VOICEOVER_GUIDE.md): it gives
each scene's start time, length, text and pronunciation. If a take needs a different length, change
that scene in `14_NARRATION_V2.md`, run `build_v2.py`, and render again.
