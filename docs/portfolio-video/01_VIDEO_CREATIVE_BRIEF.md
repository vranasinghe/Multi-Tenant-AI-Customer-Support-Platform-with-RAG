# Creative brief

## The one idea

**An engineering case study you can check.** The product is shown working; each hard problem is
shown with its cause, its fix and its evidence; and what is unproven is said out loud. The honesty
is the differentiator, so it gets the same design care as the achievements.

## Deliverables

| | Video A: showcase | Video B: documentary |
|---|---|---|
| Length | 80 s (limit 60–90) | 10:00 |
| Job | Make a recruiter want the long one | Let an engineer judge the work |
| Script | [02](02_CINEMATIC_TRAILER_SCRIPT.md) | [03](03_FULL_DOCUMENTARY_SCRIPT.md) |
| Footage | Excerpts of the same clips | All clips |

## Audience and reading order

Recruiters and non-technical viewers get the problem and the product first (scenes 1–3).
Engineers get architecture, retrieval, isolation and failures (4–8). Managers get method and
status (9–11). Every technical term is explained in one clause the first time it is spoken.

## Tone

Calm, specific, first person only where a contribution is confirmed. No superlatives, no urgency,
no "revolutionary". A limitation is stated in the same voice as a result.

## Visual identity

| Token | Hex | Use |
|---|---|---|
| Background | `#080C14` | Every non-footage frame |
| Surface | `#111827` | Cards, diagram nodes, window chrome |
| Primary blue | `#2563EB` | Request paths, key lines, progress |
| Accent blue | `#38BDF8` | Highlights, cursor, labels |
| Primary text | `#FFFFFF` | Headlines |
| Secondary text | `#94A3B8` | Explanations |
| Green | `#22C55E` | Verified successful results only |
| Amber | `#F59E0B` | Limitations, unverified items, controlled overload |
| Red | `#EF4444` | Actual failures and found defects only |

- **Type:** Inter (headlines 700, body 400/500); JetBrains Mono for code and terminal. Both are
  open-source (SIL OFL): install before opening the SVGs.
- **Grid:** 12 columns at 1920×1080, 96 px side margins, 24 px gutters. 4K is the same ×2.
- **App footage:** the dashboard is a light interface. Seat it in a rounded 16 px window on
  `#080C14` with a soft shadow; do not recolour or "dark mode" it, which would show a UI that does
  not exist.
- **Motion:** 400–600 ms ease-in-out; one thing moves at a time; connections draw in the direction
  data travels.
- **Avoid:** particles, glitch transitions, holograms, robot imagery, stock footage, tiny code.

## Two permanent on-screen labels

1. [label-demo.svg](assets/label-demo.svg) on **every** shot with a chat answer, retrieval score or
   analytics card: "Deterministic local demonstration · canned demo reply · hash embeddings".
2. [label-local.svg](assets/label-local.svg) on every results graphic: "Local validation · not
   production · not independently certified".

Graphics also carry **MEASURED** (green outline, from an artifact) or **ILLUSTRATIVE** (amber
outline, explains a mechanism).

## Success test

A viewer can answer, after Video B: What does it do? How are tenants kept apart? What broke, and
how do you know it is fixed? What has not been proven yet?
