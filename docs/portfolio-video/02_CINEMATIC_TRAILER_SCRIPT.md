# Video A — flagship showcase (80 seconds)

Narration blocks here are the source for [07](07_VOICEOVER_SCRIPT.md) and the subtitles. After
editing them, run `python docs/portfolio-video/subtitles/build.py`.

Clip IDs `R..` are in [05](05_SCREEN_RECORDING_CHECKLIST.md); diagrams `D..` in
[06](06_MOTION_GRAPHICS_PLAN.md). Demo label = [label-demo.svg](assets/label-demo.svg).

## Scene A1 — Hook (0:00–0:10, 10 s)

**Narration**
> One platform serving many businesses. Each brings its own documents, customers and
> conversations, and none of that should ever cross over.

**On-screen text:** Many businesses. One platform. Kept apart.
**Footage:** 1 s each: R15 dashboard, R04 documents, R09 widget, R12 inbox.
**Animation:** Four windows slide into a 2×2 grid, then separate along a thin blue divider.
**Sound:** Low pulse; one soft click per window.

## Scene A2 — The product (0:10–0:23, 13 s)

**Narration**
> This is a multi-tenant AI customer support platform. A business adds its documents and website,
> sets up a chatbot, and embeds it on its own site.

**On-screen text:** Multi-Tenant AI Customer Support Platform with RAG
**Footage:** R03 wizard (speed ×2), R04 Queued → Processing → Ready.
**Animation:** Title wipes in left to right and holds 3 s.
**Sound:** Music enters.

## Scene A3 — It works (0:23–0:43, 20 s)

**Narration**
> Answers stream back with their sources, and every conversation reaches a team inbox. This
> recording uses an offline demo model, so the reply is a fixed sentence. The retrieval, the
> streaming and the citation behind it are real.

**On-screen text:** Streaming · Sources · Inbox
**Footage:** R07 answer and citation; R09 widget on the fictional store; R12 transcript. Demo label on all.
**Animation:** Blue outline traces the citation line, then follows it into the inbox shot.
**Sound:** Subtle key taps.

## Scene A4 — Underneath (0:43–0:57, 14 s)

**Narration**
> Underneath is a Next.js dashboard, a FastAPI backend, PostgreSQL with vector search, and Redis
> driving background workers. It is one modular monolith, running as several processes in
> containers.

**On-screen text:** Next.js · FastAPI · PostgreSQL + pgvector · Redis + Celery
**Footage:** [D01](diagrams/D01-architecture.svg).
**Animation:** Layers D01 in order: clients, API, data, workers.
**Sound:** Rising pad.

## Scene A5 — Evidence (0:57–1:12, 15 s)

**Narration**
> An audit found seven problems. All seven now have passing local evidence, backed by fifteen
> hundred and five passing tests. Real AI quality and production readiness are still unproven.

**On-screen text:** 7 of 7 findings: local pass · 1,505 tests passing locally · AI quality and production: not yet verified
**Footage:** [D10](diagrams/D10-remediation-timeline.svg), then [D11](diagrams/D11-test-growth.svg). Local label.
**Animation:** Seven nodes turn green; the third text line appears in amber and holds 2 s.
**Sound:** Seven quiet ticks; music drops under the amber line.

## Scene A6 — Close (1:12–1:20, 8 s)

**Narration**
> Software engineering, full-stack development and applied AI. Read the full case study at venuja
> dot online.

**On-screen text:** Multi-Tenant AI Customer Support Platform with RAG · Software Engineering · Full-Stack Development · AI Engineering · venuja.online
**Footage:** [End card](assets/end-card.svg).
**Animation:** Blue line draws a frame around the title; fade to `#080C14`.
**Sound:** Final chord, 1 s tail.
