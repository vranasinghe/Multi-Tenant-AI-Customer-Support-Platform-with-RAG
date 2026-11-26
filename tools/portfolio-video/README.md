# Portfolio video workspace

Remotion compositions for the portfolio videos. It has its own `package.json` and lockfile and is
not part of the application's pnpm workspace. The production documents in
`docs/portfolio-video/` are the source of truth.

| Composition | Length | Output in `output/video/final/` |
|---|---|---|
| `PortfolioShowcaseV2` | 90 s | `showcase-preview-v2.mp4` |
| `EngineeringDocumentary` | 11 min 37 s | `documentary-preview.mp4` |
| `PortfolioShowcase` | 80 s | `showcase-preview.mp4`, the original, kept for comparison and not re-rendered |

All are 1920×1080, 30 fps, H.264.

## Commands (PowerShell, from this folder)

```powershell
npm ci
```

```powershell
npm run prepare-media
```

```powershell
python ../../docs/portfolio-video/subtitles/build_v2.py
```

```powershell
npm run studio
```

```powershell
npm run render:showcase
```

```powershell
npm run render:documentary
```

```powershell
node scripts/render.mjs documentary --only 6,7
```

```powershell
python scripts/qa.py ../../output/video/final/documentary-preview.mp4 697
```

```powershell
python scripts/compare.py
```

Run `prepare-media` first: it probes the recordings in `output/video/portfolio/clips/`, makes
H.264 proxies, copies the diagrams and extracts the source and test-artifact excerpts. It never
writes to the originals.

The documentary is rendered one chapter at a time into `output/video/final/parts/documentary/` and
joined without re-encoding. `--only` re-renders the named chapters and rejoins; `--resume` keeps
chapters that already exist. Use either only when nothing shared between chapters changed.

`node scripts/stills.mjs <CompositionId> <folder> <frame...>` writes review stills, and
`python scripts/sheet.py <folder> <out prefix>` combines them.

**Needs:** Node 24, Google Chrome (set `CHROME_PATH` if it is not in the default place), Python
with `opencv-python` for the Python scripts. FFmpeg and ffprobe come with Remotion. No separate
browser is downloaded.

## Narration, music and timing

Scene lengths and subtitles are generated from
[14_NARRATION_V2.md](../../docs/portfolio-video/14_NARRATION_V2.md): edit the text there and run
`build_v2.py`. How to record is in
[15_VOICEOVER_GUIDE.md](../../docs/portfolio-video/15_VOICEOVER_GUIDE.md), and the file names are in
[public/audio/README.md](public/audio/README.md).

After the voice is recorded, re-time the subtitles, then

```powershell
node scripts/render.mjs documentary --final --captions-retimed --privacy-reviewed
```

which writes `documentary-final.mp4` and its `.srt` (`showcase-v2` writes `showcase-final.mp4`). It
is refused without the voice file and both flags. The flags are your statement that you did those
checks; nothing verifies them.

## Rules the code follows

- Application footage is shown in its real light theme; it is cropped and zoomed, never retouched.
- Diagrams are animated by their own `step-N` groups; labels and values are not rewritten.
- Source code and test output on screen are extracted from repository files by
  `scripts/excerpts.mjs` and labelled as excerpts, never styled as a running terminal.
- Chat and retrieval shots carry the demo label; results carry the local-validation label.
- `R08` frames 204–237 are removed from its proxy (the public key was visible there). Do not use
  the original R08 file directly.

## Licensing

Remotion is free for individuals and organizations of up to three people
([licence](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)); no key is configured.
Inter and JetBrains Mono are under the SIL Open Font License.
