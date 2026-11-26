# Motion graphics plan

Editable SVGs in [diagrams/](diagrams), 1920×1080 (scale to 3840×2160 without loss). Regenerate
with `python docs/portfolio-video/diagrams/build_diagrams.py` — manual edits to an SVG are
overwritten, so either edit the generator or copy the SVG first.

## Shared rules

- Fonts: Inter; JetBrains Mono for code. Install before opening.
- Layers are groups `step-1 … step-N`, plus `heading`, `footnote`, `legend`. `heading` and
  `legend` are on screen from frame 0; reveal steps in order.
- Default reveal: 12 frames (400 ms), opacity 0→1 with 16 px upward move, ease-out. Hold at least
  1.5 s before the next step.
- Connections draw with a trim path in the arrow's direction (15 frames).
- Line language, identical everywhere: solid blue = synchronous request; dotted accent = SSE;
  grey dashes = background job; solid white = database transaction; violet = object storage;
  dash-dot accent = AI provider; amber dashes = controlled rejection; green = verified; red =
  failure.
- Badges stay visible: **MEASURED · LOCAL** (artifact values), **FROM SOURCE CODE**,
  **ILLUSTRATIVE** (mechanism, invented content), **PLANNED · NOT BUILT**.
- Footnotes are the evidence. They may be small on screen but must stay in the frame.

## Diagram by diagram

| ID | File | Used in | Seconds | Animation |
|---|---|---|---|---|
| D01 | [architecture](diagrams/D01-architecture.svg) | A4, 01, 04, 12 | 55 | 1 clients → 2 web and API with SSE pulse looping → 3 data stores, transaction flash → 4 workers, dashed jobs move → 5 providers. Zoom 130% on each group while narrated, end on full view |
| D02 | [tenant isolation](diagrams/D02-tenant-isolation.svg) | 06 | 25 | 1 both orgs → layers 2–5 slide in → 6 two row sets → 7 red request travels and stops at layer 2 |
| D03 | [RAG pipeline](diagrams/D03-rag-pipeline.svg) | 05 | 40 | Steps 1–6 as a packet moving right; 7–8, then 13 forks retrieval into two lanes and merges; 9–12; 14 amber card last |
| D04 | [workers](diagrams/D04-celery-workers.svg) | 04, 07 | 20 | api and beat → queues fill → worker claims → parser child pulses amber → maintenance → stores |
| D05 | [pool starvation](diagrams/D05-pool-starvation.svg) | 07 | 14 | Requests stack → ten slots fill red one by one → return arrow → timeout card shakes once → measured line |
| D06 | [admission control](diagrams/D06-admission-control.svg) | 07 | 14 | One request walks 1–6; a burst follows, extras drop to 429/503; result card |
| D07 | [citation provenance](diagrams/D07-citation-provenance.svg) | 05, 07 | 16 | Candidates → authorize → C greys out → answer types → [3] struck through |
| D08 | [immutable storage](diagrams/D08-immutable-storage.svg) | 07 | 14 | Four stages → red stale attempt rises and bounces off Publish → reclaim card |
| D09 | [widget lifecycle](diagrams/D09-widget-lifecycle.svg) | 08 | 11 | Follow the loop: tag → registry → identity → exists/new → frame → destroy → mount |
| D10 | [remediation timeline](diagrams/D10-remediation-timeline.svg) | A5, 09 | 16 | Line draws; seven checks pop at 8-frame intervals; amber “still open” card holds |
| D11 | [test growth](diagrams/D11-test-growth.svg) | A5, 09 | 12 | Bars grow left to right to their labelled values; Phase 7 divider before A4 |
| D12 | [capacity](diagrams/D12-performance.svg) | 09, 12 | 14 | Gate line first, then runs; the 1,975 ms bar lands last in amber |
| D13 | [backup and restore](diagrams/D13-backup-restore.svg) | 09 | 10 | Left to right; red defect card appears and holds before the metrics |
| D14 | [roadmap](diagrams/D14-roadmap.svg) | 11 | 28 | Green, amber, grey columns in turn; grey never turns green |

## Scene 02 illustrations (no SVG supplied)

Build in the editor from simple shapes: (1) three identical speech bubbles stacking;
(2) file and globe icons scattered, then gathering; (3) a clock with a hand sweeping;
(4) two labelled columns with a divider. Flat, two colours, no people or robot artwork, no numbers.

## Overlays and cards

| File | Use |
|---|---|
| [label-demo.svg](assets/label-demo.svg) | Top-right, 48 px inset, every chat, retrieval and analytics shot |
| [label-local.svg](assets/label-local.svg) | Every results graphic and terminal shot |
| [title-card.svg](assets/title-card.svg) | Scene 01 title |
| [end-card.svg](assets/end-card.svg) | A6, scene 12 |

## Illustrative versus measured

Counters may animate **to** a measured value; they may not overshoot or invent in-between points on
a chart. No chart may be added without an artifact. D05–D07 mechanics are schematic even where
their numbers are measured.
