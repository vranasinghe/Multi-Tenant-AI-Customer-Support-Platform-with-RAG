# Editing timeline and instructions

## Project settings

| Setting | Value |
|---|---|
| Timeline | 1920×1080, 30 fps. The draft screen clips are 1080p, so **export 1080p**. Use 4K only if every screen clip is re-recorded at 4K |
| Video export | H.264 MP4, High profile, yuv420p, VBR 2-pass, 12 Mbps target / 16 max (4K: 45 / 60) |
| Audio export | AAC 320 kbps, 48 kHz, stereo, −14 LUFS integrated, −1 dBTP |
| Subtitles | Burn in nothing by default; upload the `.srt` files. For social copies, burn in |
| Colour | Rec.709. Footage is not graded: set only the surround and graphics to the palette |

Suggested tools: DaVinci Resolve (free) for edit and audio; After Effects, Resolve Fusion or Figma
plus Jitter for the SVG reveals.

## Tracks

V5 labels (demo / local) · V4 text · V3 highlights and zoom boxes · V2 footage window or diagram ·
V1 background `#080C14` · A1 voice · A2 interface sounds · A3 music.

## Order of work

1. Record voice first, one scene per take. Re-time the scene lengths to the voice, keeping totals
   within 60–90 s (A) and about 10:00 (B).
2. Lay voice on A1, then place footage and diagrams from [04](04_STORYBOARD.md).
3. Reveal diagram layers on the spoken noun they illustrate ([06](06_MOTION_GRAPHICS_PLAN.md)).
4. Add zooms, highlights, labels, then sound and music.
5. Re-time subtitles: in Resolve, import the `.srt` and drag cues to the waveform. If you change
   narration text, edit 02/03 and run `subtitles/build.py` first.

## Voice processing

High-pass 80 Hz → light noise reduction (do not gate hard) → gentle de-esser → compressor 3:1,
3–6 dB reduction → limiter. Remove long breaths, keep natural pauses.

## Music and sound

- One calm instrumental bed, 80–100 BPM, no vocals. Duck to −24 to −28 LUFS under voice.
- **Licence it for YouTube and your own website** (YouTube Audio Library, or a paid library whose
  licence covers both). Save the licence or terms as a file in `assets/licences/` and credit it in
  the description if required.
- Interface sounds: soft clicks and ticks only, 12 dB under voice. No whooshes on every cut.

## Zooming into the interface

- Start every new screen **unzoomed for at least 1.5 s** so the viewer knows where they are.
- Maximum 160%. Above that, 1080p text softens: crop tighter at recording time instead.
- Zoom in 18 frames, hold at least 2 s, zoom out 15 frames. One zoom per sentence at most.
- Keep the sidebar or page title visible when possible.
- Highlight with a 3 px `#38BDF8` rounded outline and dim the rest to 55%. Never cover text.
- Cursor emphasis is already in the footage; do not add a second cursor.
- Text smaller than 24 px on the 1080p frame is not readable on a phone: zoom or typeset it.
- Speed-ups (typing, wizard) show a small “×2.5” tag. Never cut so that a failure or wait appears
  not to exist; processing waits may be sped up, with the tag.

## Transitions

Cuts by default. 8-frame cross-dissolve between scenes. Match-cut a diagram node to the next
diagram (D01 `worker` → D04). No 3D spins, glitches, light leaks or particles.

## Cut sheet — Video A

| In | Out | Footage | Edit note |
|---|---|---|---|
| 0:00 | 0:10 | R15, R04, R09, R12 | Grid; 1 s on each before parting |
| 0:10 | 0:17 | R03 ×2.5 | Title over 60% scrim |
| 0:17 | 0:23 | R04 | Status column zoom 140% |
| 0:23 | 0:30 | R07 | Source line 160% |
| 0:30 | 0:37 | R09 | Widget crop |
| 0:37 | 0:43 | R12 | Sources |
| 0:43 | 0:57 | D01 | Four reveals, 3 s apart |
| 0:57 | 1:12 | D10, D11, text card | Amber line holds 4 s |
| 1:12 | 1:20 | end card | Fade last 12 frames |

## Cut sheet — Video B

Scene in-points: 0:00, 0:25, 0:55, 2:10, 3:20, 4:20, 5:15, 6:30, 7:15, 8:30, 9:10, 9:40, end 10:00.
Shot in-points are in the storyboard. Add YouTube chapters at these times
([10](10_YOUTUBE_TITLE_DESCRIPTION.md)); if the voice shifts them, update the chapters.

## Reusing between the two

Edit B first. Build A in a second timeline from the same nested clips, so a corrected shot or
number changes in one place.

## Never

Retouch or retype application text; add a notification the app did not show; draw a chart with
no artifact; mock a terminal; replace the demo reply with a better-sounding answer.
