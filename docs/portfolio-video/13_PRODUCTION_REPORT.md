# Production report — showcase preview

26 November 2026. **One video has been rendered: a silent preview of Video A, for your review. It
is not a publishable final.** The documentary has not been built or rendered.

## Outputs

| File | What | Size | Status |
|---|---|---|---|
| `output/video/final/showcase-preview.mp4` | 80.0 s, 2400 frames, 1920×1080, 30 fps, H.264 High, yuv420p, **no audio stream** | 6.5 MB | Rendered, checks passed |
| `output/video/final/qa/showcase-preview-report.json` | ffprobe and frame checks | | |
| `output/video/final/qa/showcase-preview-contact.png` (and `-1` … `-3`) | One frame every half second | | |
| `output/video/final/qa/stills/` | 18 scene stills and the component gallery | | |
| `output/video/final/qa/footage-contact-sheet.png`, `footage-report.json` | Source clip review | | |
| [tools/portfolio-video/](../../tools/portfolio-video/README.md) | Remotion project | | Type check and repository format check pass |

`output/video/` is gitignored. Nothing was committed or pushed.

Not produced: `documentary-preview.mp4`, `showcase-final.mp4`, `documentary-final.mp4`, final
`.srt` files, `thumbnail.png`.

## Checks on the rendered file

| Check | Result |
|---|---|
| Resolution, frame rate, codec, frame count, duration | Pass |
| Empty frames (every frame decoded) | None flagged |
| Privacy and cropping (human review of the half-second sheets) | No key, token, password, cookie, local path or real person seen. Visible: synthetic `@example.com` address in the sidebar, fictional names, demo dates |
| Token and cost line, model-selection step, analytics, “Getting started” panel | Not shown |
| Demo label on chat shots; local label on results | Present |
| Audio sync | Not applicable: no audio |
| Subtitles | Draft timings burned in; **not** matched to any voice |

A half-second review can miss a very short flash. Watch the whole file once before sharing.

## Footage

All 15 clips R01–R15 exist and decode completely (declared frames equal decoded frames):
1920×1080, 30 fps, MPEG-4 Part 2, no audio, 266 s, 95 MB. None is missing. Originals are unchanged.
The old recordings in `output/video/` were not used.

**Correction to earlier documents:** `R08` shows the widget's public key and installation script
**unblurred** for frames 211–230 (7.0–7.7 s). I had stated they were blurred. The showcase does not
use R08; its proxy now removes frames 204–237, and the recorder applies the mask before opening the
tab (not re-recorded). The key belonged to a disposable stack that has been deleted. The raw frames
remain in the gitignored `output/video/portfolio/frames/`.

## Where the preview departs from the script or storyboard

| Change | Reason |
|---|---|
| The wizard's model step is skipped | It lists real model names, and no real model was run |
| A5 shows the 1,505 total with a per-suite breakdown, then a two-column card | The narration says 1,505 while D11 charts only the backend |
| A4 shows D01 without its heading, cropped to the content | Legibility; the source footnote stays |
| The playground shot is a wide strip | Keeps the token and cost line out of frame |

The 80-second script does not include the capacity example (67 served, 33 rejected, P95 1,682 ms,
25 ms margin), the widget size or the restore rehearsal. Those belong to the documentary.

## Please judge in review

1. **Opening montage:** four small windows read as texture, not as readable UI. Intended?
2. **A4:** the architecture builds slowly and is dense; labels will be hard to read on a phone.
3. **Pacing** without a voice: especially the 3-second test-growth chart in A5.
4. **Demo reply:** the fixed sentence appears three times in A3.
5. **Visual direction** overall, before the documentary is built the same way.

## Claims re-checked

The 439 source files from the final validation run are unchanged, and no newer evidence exists, so
no figure changed. Milestone closure still waits on the migration policy decision; hosted CI, real
AI evaluation and deployment are still not done. Test suites were not re-run.

## Publication blockers

- [ ] Your review of this preview
- [ ] Narration recorded (`public/audio/showcase-voice.wav`)
- [ ] Music chosen with a saved licence, or no music
- [ ] Subtitles re-timed to the voice
- [ ] Full-length privacy viewing
- [ ] `venuja.online` carries the case study the end card points to
- [ ] Undergraduate rules on AI-assisted work and sharing checked, if assessed
- [ ] Documentary only: contribution claims C1–C10 confirmed
- [ ] Repository link only after the reviewed code is pushed and approved (still excluded)

## Dependencies added (isolated)

`remotion`, `@remotion/cli`, `@remotion/bundler`, `@remotion/renderer` 4.0.547; `react`,
`react-dom` 19.3.1; `@fontsource/inter`, `@fontsource/jetbrains-mono`; `typescript` 6.0.3 and React
types. About 550 MB in `tools/portfolio-video/node_modules`. Rendering uses the installed Chrome.
The application's manifests and lockfile were not changed.
