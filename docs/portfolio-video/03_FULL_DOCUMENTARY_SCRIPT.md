# Video B — technical case study (10:00)

Narration blocks here are the source for [07](07_VOICEOVER_SCRIPT.md) and the subtitles. After
editing them, run `python docs/portfolio-video/subtitles/build.py`.

Facts: [00](00_PROJECT_FACT_CHECK.md). Clips `R..`: [05](05_SCREEN_RECORDING_CHECKLIST.md).
Diagrams `D..`: [06](06_MOTION_GRAPHICS_PLAN.md).

**Before recording scene 10**, answer C1–C10 in [00 §9](00_PROJECT_FACT_CHECK.md). **On the day you
record**, re-check scene 11 against the newest evidence (MIG-02, hosted CI, real providers).

## Scene 01 — Opening (0:00–0:25, 25 s)

**Narration**
> What does it take to engineer an AI customer support platform that can serve multiple
> businesses while keeping their knowledge, conversations, and customer data isolated?
>
> This case study shows the working product, the architecture behind it, what broke along the way,
> and what is still unproven.

**On-screen text:** Multi-Tenant AI Customer Support Platform with RAG · A technical case study
**Footage:** Montage, 2 s each: R15, R04, R08, R09, R12, then D01.
**Animation:** Shots pass behind a dark scrim; at 0:15 they collapse into the title.
**Sound:** Low pulse building; hit on the title.
**Facts:** F-03, F-05, F-09, F-10.

## Scene 02 — The problem (0:25–0:55, 30 s)

**Narration**
> Customers ask the same questions again and again. The answers usually exist, spread across
> policy documents and web pages, but someone has to find them each time. A support assistant
> grounded in a business's own material can help. And if one shared platform serves many separate
> businesses, every answer has to come from the right one, and only that one.

**On-screen text:** Repeated questions · Scattered knowledge · Manual effort · One platform, strict separation
**Footage:** Motion graphics only: speech bubbles, scattered file icons, then two separate columns.
**Animation:** Files drift into two labelled columns; a solid line forms between them.
**Sound:** Soft paper sounds; one clean tone when the divider closes.
**Facts:** Problem statement from [PRD](../PRD.md) §2. No savings or adoption figures.

## Scene 03 — Product walkthrough (0:55–2:10, 75 s)

**Narration**
> Here is the real application, running locally with fictional data. An owner signs in and lands on
> the organization dashboard. A short wizard creates a chatbot. Documents are uploaded, and a
> background worker takes each one from queued, to processing, to ready. You can inspect the
> passages it produced and test which ones a question retrieves. Websites can be added too; here
> the crawler refuses a private network address.
>
> In the playground, a question streams back with a numbered source. One important note: this is a
> deterministic demonstration. The reply is a fixed sentence, not an AI answer. What is real is the
> retrieval, the streaming and the citation. An unrelated question gets a fallback instead.
>
> Once the bot is active and the website's origin is verified, a visitor asks through the embedded
> widget. The team sees that conversation in the inbox, marks it resolved, and analytics update
> from stored events.

**On-screen text:** Sign in → Create → Upload → Retrieve → Test → Embed → Review (progress strip)
**Footage:** R01 (4 s), R02 (3 s), R03 (9 s), R04 (9 s), R05 (6 s), R06 (6 s), R07 (14 s), R08 (6 s), R09 (7 s), R12 (7 s), R13 (4 s). Demo label from R05 on.
**Animation:** Progress strip fills; zooms per [08](08_EDITING_TIMELINE.md).
**Sound:** Music low; light UI clicks.
**Facts:** F-01 – F-11. Crop analytics to the cards (X8, X9).

## Scene 04 — Architecture (2:10–3:20, 70 s)

**Narration**
> The system is a modular monolith: one Python codebase and one database, run as several
> processes. That is not microservices, even though there are several containers.
>
> The Next.js and React dashboard talks to a FastAPI backend over ordinary requests. Dashboard
> requests are authenticated and checked against the member's role. Chat answers come back from the same API as
> a stream of server-sent events. The widget on a customer's site is a small loader that opens an
> isolated frame.
>
> PostgreSQL holds relational data and vectors, using the pgvector extension. Private object
> storage keeps the original files. Language and embedding models sit behind provider adapters.
>
> Slow work leaves the request path. Redis carries the queue to Celery workers, which parse, chunk
> and embed documents. A scheduler triggers a recovery sweep on its own maintenance worker, so
> busy ingestion cannot delay it. Everything runs in Docker containers.

**On-screen text:** Modular monolith · Request path · SSE stream · Background jobs
**Footage:** [D01](diagrams/D01-architecture.svg), [D04](diagrams/D04-celery-workers.svg).
**Animation:** Solid blue = synchronous; accent pulses = SSE; dashed = background; cylinders glow on a transaction. Layer order in [06](06_MOTION_GRAPHICS_PLAN.md).
**Sound:** Distinct soft tone per path type.
**Facts:** F-12, F-20 – F-25.

## Scene 05 — The retrieval pipeline (3:20–4:20, 60 s)

**Narration**
> Retrieval augmented generation means finding evidence first, then writing from it. A file or web
> page is extracted into text, cleaned, and split into overlapping chunks that never cross a
> heading. Each chunk gets an embedding, a list of numbers, stored beside the text.
>
> A question is searched two ways: vector search compares embeddings, keyword search matches words,
> and the two rankings are merged. Retrieval is always scoped to one organization and one chatbot.
> The prompt is assembled, the model streams, and citations are validated on the way out.
>
> Citation provenance proves a source was shown to the model, not that it supports the sentence.
> Offline, with a word-matching stand-in for embeddings, the answer appeared in the top five for
> eighty-five percent of cases, below the ninety percent target. Real model accuracy is untested.

**On-screen text:** Hybrid retrieval: vector + keyword, merged by rank · Answer-bearing Recall@5: 85% (target 90%) · offline hash baseline · Provenance ≠ correctness
**Footage:** [D03](diagrams/D03-rag-pipeline.svg), [D07](diagrams/D07-citation-provenance.svg), 4 s of R05.
**Animation:** A packet travels D03; search splits into two lanes and merges. The 85% card is amber.
**Sound:** Stepped ticks per stage; music thins under the amber card.
**Facts:** F-30 – F-38, X7.

## Scene 06 — Keeping businesses apart (4:20–5:15, 55 s)

**Narration**
> Take two fictional businesses. Each has its own chatbot, documents and conversations. Here the
> second owner opens the first one's address, and gets organization not found.
>
> Several layers enforce this. Sessions live on the server, in a cookie scripts cannot read. Roles
> decide what each member may do. Queries are scoped to the organization, and PostgreSQL
> enforces forced row-level security underneath, so a missed filter is not enough to leak a row.
>
> Public widgets receive short-lived tokens limited to one conversation, and visitors get only the
> fields they need. Forwarding headers are trusted only from listed proxies, and AI providers must
> use HTTPS. This is tested design, not a security certification.

**On-screen text:** RBAC · Server sessions · FORCE row-level security · Scoped widget tokens · Minimal public data
**Footage:** [D02](diagrams/D02-tenant-isolation.svg), R14, then a card with the two status codes from `tenant-isolation-statuses.txt`.
**Animation:** Request from B hits the membership check and stops; layers light inward.
**Sound:** Low thud on refusal, no alarm.
**Facts:** F-40 – F-49.

## Scene 07 — What broke, and how it was fixed (5:15–6:30, 75 s)

**Narration**
> An audit then found problems that the existing, passing tests had missed.
>
> First, ten simultaneous chats exhausted the database connection pool. Each request held one
> connection while asking for another. The fix releases it early, keeps transactions short, and
> queues or refuses extra work. At one hundred concurrent requests, sixty-seven were served,
> thirty-three were politely refused, and none failed.
>
> Second, a source cut from the prompt could still be cited. Now only sources actually rendered can
> be cited, even midway through a stream.
>
> Third, a hostile document could tie up a worker. Each parse now runs in a fresh process with time
> and memory limits, and a failed attempt leaves the previous version in place. That is
> containment, not yet a security sandbox.
>
> Fourth, found while fixing that one, a stale crawl could overwrite newer stored pages. Every
> write now gets a new object key, published only by the attempt that still owns the job.

**On-screen text:** Problem → Root cause → Solution → Validation (four identical cards)
**Footage:** [D05](diagrams/D05-pool-starvation.svg) → [D06](diagrams/D06-admission-control.svg) → [D07](diagrams/D07-citation-provenance.svg) → [D04](diagrams/D04-celery-workers.svg) → [D08](diagrams/D08-immutable-storage.svg). Code inserts: C-1 to C-4 in [05](05_SCREEN_RECORDING_CHECKLIST.md).
**Animation:** Each card: red problem, neutral cause, blue fix, green validation. Amber "containment ≠ sandbox" holds 3 s.
**Sound:** Same four-note motif per challenge.
**Facts:** F-50 – F-54.

## Scene 08 — The widget (6:30–7:15, 45 s)

**Narration**
> The widget has to behave on websites it does not control. Adding the same script twice keeps one
> instance. A second instance must be asked for. Destroying it removes the frame and its listener,
> so single-page applications can remount safely. An anonymous visitor's conversation resumes
> after a reload, and an interrupted answer is recorded as interrupted. It adapts to a phone
> screen. The loader is five thousand two hundred and forty-eight bytes compressed, against a
> budget of ten thousand two hundred and forty. These journeys were tested in Chrome only.

**On-screen text:** 1 instance per identity · destroy() · Resume · 390 px · Loader 5,248 B gzip / 10,240 B budget · Chrome only
**Footage:** R10 (14 s), R09 reload part (10 s), R11 (10 s), [D09](diagrams/D09-widget-lifecycle.svg) (11 s).
**Animation:** Frame counter highlighted as it reads 1, 1, 2, 1, 2. Budget bar fills to 51%.
**Sound:** Click per state change.
**Facts:** F-55, F-56. Interrupted streams: report evidence, not footage.

## Scene 09 — How it was validated (7:15–8:30, 75 s)

**Narration**
> The method was audit driven. Build the initial system, measure a baseline, record findings, fix
> one at a time with a failing test first where possible, stabilize performance, then validate the
> whole thing together.
>
> The audit raised seven findings, from the connection pool to the widget. All seven now pass
> locally. The reported results: twelve hundred and nine backend tests, seventeen proxy tests run
> separately, two hundred and sixty-two frontend unit tests, and seventeen browser journeys.
> That is fifteen hundred and five.
>
> To check the tests themselves, fixes were deliberately broken ten times, and each break was
> caught. The capacity gate passed ten of ten declared runs, once with only twenty-five
> milliseconds to spare. A backup and restore rehearsal passed, and exposed a permissions bug,
> now fixed.
>
> The self-audit score moved from eighty and a half to eighty-five point seven five. These are
> local results, not independent certification, and hosted CI has not run yet.

**On-screen text:** AUD-01 … AUD-07 · 1,505 passing (local) · 10/10 breaks caught · 10/10 capacity runs · Self-audit 80.5 → 85.75 · Hosted CI: not run
**Footage:** [D10](diagrams/D10-remediation-timeline.svg), [D11](diagrams/D11-test-growth.svg), terminal T-1 to T-4, [D12](diagrams/D12-performance.svg), [D13](diagrams/D13-backup-restore.svg), CI file T-5.
**Animation:** Counters run only to values on the cited artifact. The 25 ms run is amber.
**Sound:** Quiet ticks; no celebratory sting.
**Facts:** F-60 – F-70.

## Scene 10 — My contribution (8:30–9:10, 40 s)

**Narration**
> This is my undergraduate portfolio project, built with AI coding assistants including Codex and
> Claude Code, so I will not claim every line was typed by hand. What I want you to judge is the
> process: written requirements with explicit acceptance rules, a baseline before changes, an audit,
> focused fixes with retained failures, and decisions held for approval instead of assumed. Ask me
> about any trade-off in this video, including the ones that did not work out the first time.

**On-screen text:** Built with AI coding assistants · Requirements → Audit → Fix → Evidence → Decision
**Footage:** Slow scroll of [MVP_IMPROVEMENT_PLAN.md](../MVP_IMPROVEMENT_PLAN.md) rules and the [progress tracker](../mvp-improvement/02_PROGRESS_TRACKER.md). Optionally you on camera.
**Animation:** Five-step line draws left to right.
**Sound:** Music only slightly raised.
**Facts:** [00 §9](00_PROJECT_FACT_CHECK.md). **Confirmation required.**

> This paragraph claims no specific personal task. After confirming C1–C10, replace the third
> sentence with your own list, for example: "My part was [planning / architecture decisions /
> prompt design / review / debugging / testing]." Also confirm the tool names (add Cursor if it
> applies). Keep the scene near 85 words.

## Scene 11 — Honest status and next steps (9:10–9:40, 30 s)

**Narration**
> Where it stands: the core engineering is validated locally and all seven audit findings pass.
> One migration policy decision still blocks formal milestone closure. Real AI evaluation,
> semantic answer quality, hosted CI and production deployment all remain open. Those are the
> roadmap, not existing features, which is why you are watching a controlled demonstration rather
> than an always-on public service.

**On-screen text:** Validated locally ✓ · Milestone closure: awaiting decision · Real AI, quality, hosted CI, production: open
**Footage:** [D14](diagrams/D14-roadmap.svg).
**Animation:** Green column, amber column, then grey future column.
**Sound:** Music steady, no lift.
**Facts:** §6, §7 of [00](00_PROJECT_FACT_CHECK.md).

## Scene 12 — Close (9:40–10:00, 20 s)

**Narration**
> A multi-tenant AI customer support platform with retrieval augmented generation. Software
> engineering, full-stack development and AI engineering. The full case study, with its evidence
> and its limitations, is on my portfolio at venuja dot online. Thank you for watching.

**On-screen text:** Multi-Tenant AI Customer Support Platform with RAG · Software Engineering · Full-Stack Development · AI Engineering · Portfolio: venuja.online
**Footage:** Montage R15, R04, R09, R12, D01, D12, then [end card](assets/end-card.svg). **No GitHub link** (X1).
**Animation:** Montage tiles fold into one blue line, which becomes the end-card underline.
**Sound:** Resolve and tail.
