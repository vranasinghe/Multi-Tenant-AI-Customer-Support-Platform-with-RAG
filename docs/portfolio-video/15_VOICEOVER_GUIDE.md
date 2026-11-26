# Voice-over recording guide

Generated from [14_NARRATION_V2.md](14_NARRATION_V2.md). **Do not edit here.**

## Before you record

- Quiet room, 15–20 cm from the microphone, pop filter or slightly off-axis.
- WAV, 48 kHz, 24-bit, mono. Peaks around −6 dB.
- One take per scene, one second of silence before and after. Name takes by scene id.
- Join the takes so each scene starts at its time below, then export one file per video:
  `tools/portfolio-video/public/audio/showcase-voice.wav` and `documentary-voice.wav`.
- If a take runs long, do not rush: tell the editor, the scene length can change.

## Recording steps

1. Approve or reword the **[CONFIRM]** statements in scene 8a.
2. Record from [16_VOICEOVER_SCRIPT.md](16_VOICEOVER_SCRIPT.md): stress, pauses and
   per-scene speaking times are marked there.
3. In an audio editor (Audacity is free), place each take at its scene start time, plus any
   *(+N s)* offset, with silence between.
4. Export WAV, 48 kHz, 24-bit, mono, the full length of the video, to:
   - `tools/portfolio-video/public/audio/showcase-voice.wav` (1:30)
   - `tools/portfolio-video/public/audio/documentary-voice.wav` (11:37)
5. Do not run a final render yet. Send both files for timing review: subtitles are then
   re-timed to your voice. **Audio synchronization has not been checked.**

## Pacing

Aim for 125–140 words per minute: steady, a full stop is a breath. Pause one beat before a
number and after a limitation. The rates below count written words; spoken numbers run
longer, so rehearse scenes with figures.

## Pronunciation

| Term | Say |
|---|---|
| FastAPI | “fast A-P-I” |
| pgvector | “P-G vector” |
| PostgreSQL | “post-gres Q-L” |
| Celery | “SELL-uh-ree” |
| Redis | “RED-iss” |
| RBAC | “R-back” |
| SSE | “server-sent events” |
| P95 | “ninety-fifth percentile” |
| Codex, Claude | “CO-dex”, “klawd” |
| HTTP, HTTPS | letter by letter |
| venuja.online | “venuja dot online” |
| 1,209 | “twelve hundred and nine” |
| 1,505 | “fifteen hundred and five” |
| 5,248 | “five thousand two hundred and forty-eight” |
| 80.5 → 85.75 | “eighty and a half … eighty-five point seven five” |

Chapter 8 contains first-person statements. **Confirm them, or reword, before recording**
([fact check §9](00_PROJECT_FACT_CHECK.md)).

## Showcase

**A1 · Title reveal** — starts 0:00 · 5 s · 10 words · 120 wpm

Support answers from each business's own knowledge, kept strictly apart.

**A2 · The product** — starts 0:05 · 14 s · 25 words · 107 wpm

*(+0 s)* This is a multi-tenant AI customer support platform.

*(+3.5 s)* One business gets a dashboard, a knowledge base,

*(+7 s)* an embeddable chat widget

*(+10.5 s)* and a shared team inbox.

**A3 · Capabilities** — starts 0:19 · 29 s · 56 words · 116 wpm

*(+0 s)* Documents move from queued to ready in the background.

*(+5 s)* Answers carry their sources. The reply is a fixed demo sentence, but the retrieval is real.

*(+10 s)* A second business cannot open this workspace. It gets organization not found.

*(+16 s)* A visitor's conversation survives a reload.

*(+20.5 s)* Analytics come from recorded events,

*(+24.5 s)* and installing the widget twice still keeps one.

**A4 · Architecture** — starts 0:48 · 17 s · 32 words · 113 wpm

Underneath are four layers: the experience layer, the application, data and background processing, and retrieval intelligence. It is one modular monolith running as several processes in containers, not a set of microservices.

**A5 · Evidence** — starts 1:05 · 19 s · 35 words · 111 wpm

The first audit passed five hundred and eighty-two backend tests and still found seven problems. All seven now pass locally, across fifteen hundred and five tests. Real AI quality and production readiness are still unproven.

**A6 · Close** — starts 1:24 · 6 s · 12 words · 120 wpm

Software engineering, full-stack and applied AI. Case study at venuja dot online.

*Total 1:30; about 1.3 minutes of speech at 130 words per minute.*

## Documentary

### Chapter 1 — Introduction and business problem

**1a · Opening** — starts 0:00 · 21 s · 46 words · 131 wpm

What does it take to engineer an AI customer support platform that can serve multiple businesses while keeping their knowledge, conversations, and customer data isolated?

This case study shows the working product, the architecture behind it, what broke along the way, and what is still unproven.

**1b · The business problem** — starts 0:21 · 27 s · 60 words · 133 wpm

Customers ask the same questions again and again. The answers usually exist, spread across policy documents and web pages, but someone has to find them each time. A support assistant grounded in a business's own material can help. And if one shared platform serves many separate businesses, every answer has to come from the right one, and only that one.

### Chapter 2 — Product demonstration

**2a · Set up knowledge** — starts 0:48 · 31 s · 69 words · 134 wpm

*(+0 s)* Here is the real application, running locally with fictional data.

*(+5 s)* An owner signs in and lands on the organization dashboard.

*(+9.5 s)* A short wizard creates a chatbot.

*(+13.5 s)* Documents are uploaded, and a background worker takes each one from queued, to processing, to ready.

*(+20 s)* You can inspect the passages it produced and test which ones a question retrieves.

*(+26 s)* Websites can be added too; here the crawler refuses a private network address.

**2b · Ask a question** — starts 1:19 · 21 s · 47 words · 134 wpm

In the playground, a question streams back with a numbered source. One important note: this is a deterministic demonstration. The reply is a fixed sentence, not an AI answer. What is real is the retrieval, the streaming and the citation. An unrelated question gets a fallback instead.

**2c · Customers and the team** — starts 1:40 · 19 s · 42 words · 133 wpm

Once the bot is active and the website's origin is verified, a visitor asks through the embedded widget. The team sees that conversation in the inbox, marks it resolved, and analytics update from stored events. The figures here are synthetic demonstration data.

### Chapter 3 — System architecture

**3a · Experience layer** — starts 1:59 · 19 s · 42 words · 133 wpm

The system is a modular monolith: one Python codebase and one database, run as several processes. Think of it in four layers. First, experience: a Next.js and React dashboard, and a small widget that opens an isolated frame on a customer's site.

**3b · Application layer** — starts 2:18 · 13 s · 28 words · 129 wpm

Second, the application. FastAPI handles ordinary requests. Dashboard requests are authenticated and checked against the member's role, and chat answers come back as a stream of server-sent events.

**3c · Data and processing layer** — starts 2:31 · 18 s · 38 words · 127 wpm

Third, data and processing. PostgreSQL holds relational data and vectors with pgvector. Private object storage keeps the original files. Redis carries the queue to Celery workers, and a scheduler triggers a recovery sweep on its own maintenance worker.

**3d · Intelligence layer** — starts 2:49 · 12 s · 25 words · 125 wpm

Fourth, intelligence: document processing, retrieval and prompt construction, with adapters for language and embedding models. This is code inside those same processes, not separate services.

**3e · The whole system** — starts 3:01 · 12 s · 24 words · 120 wpm

Together: synchronous requests, streamed answers and background jobs, in Docker containers. Several containers do not make this microservices. The detailed diagram shows each connection.

### Chapter 4 — The retrieval pipeline

**4a · From file to vectors** — starts 3:13 · 20 s · 44 words · 132 wpm

Retrieval augmented generation means finding evidence first, then writing from it. A file or web page is extracted into text, cleaned, and split into overlapping chunks that never cross a heading. Each chunk gets an embedding, a list of numbers, stored beside the text.

**4b · Search and citations** — starts 3:33 · 25 s · 55 words · 132 wpm

A question is searched two ways: vector search compares embeddings, keyword search matches words, and the two rankings are merged. Retrieval is always scoped to one organization and one chatbot. The prompt is assembled, the model streams, and citations are validated on the way out. Only sources that actually entered the prompt can be cited.

**4c · What is not established** — starts 3:58 · 21 s · 45 words · 129 wpm

Citation provenance proves a source was shown to the model, not that it supports the sentence. Offline, with a word-matching stand-in for embeddings, the answer appeared in the top five for eighty-five percent of cases, below the ninety percent target. Real model accuracy is untested.

### Chapter 5 — Multi-tenant security

**5a · Two businesses** — starts 4:19 · 13 s · 26 words · 120 wpm

Take two fictional businesses. Each has its own chatbot, documents and conversations. Here the second owner opens the first one's address, and gets organization not found.

**5b · The layers** — starts 4:32 · 21 s · 46 words · 131 wpm

Several layers enforce this. Sessions live on the server, in a cookie scripts cannot read. Roles decide what each member may do. Queries are scoped to the organization, and PostgreSQL enforces forced row-level security underneath, so a missed filter is not enough to leak a row.

**5c · Public boundaries** — starts 4:53 · 18 s · 39 words · 130 wpm

Public widgets receive short-lived tokens limited to one conversation, and visitors get only the fields they need. Forwarding headers are trusted only from listed proxies, and AI providers must use HTTPS. This is tested design, not a security certification.

### Chapter 6 — Engineering problems and solutions

**6.0 · Eleven problems** — starts 5:11 · 13 s · 28 words · 129 wpm

An audit then found problems that the existing, passing tests had missed. Here are eleven of the hardest, some from the audit and some found while fixing it.

**6.1 · Connection pool starvation** — starts 5:24 · 19 s · 40 words · 126 wpm

First, ten simultaneous chats exhausted the database connection pool: each request held one connection while asking for another. Releasing it early, short transactions and bounded admission fixed it. At one hundred concurrent requests, sixty-seven were served, thirty-three refused, none failed.

**6.2 · Citation provenance** — starts 5:43 · 19 s · 42 words · 133 wpm

Second, a source cut from the prompt could still be cited, because citations were checked against what was selected, not what was shown. Now only rendered sources can be cited, even mid-stream. Whether a source truly supports a sentence is still unverified.

**6.3 · Provider transport security** — starts 6:02 · 16 s · 33 words · 124 wpm

Third, production settings accepted a plain HTTP embedding endpoint, which could send keys and documents unencrypted. Providers now require HTTPS, refuse redirects and ignore environment proxies. No real provider endpoint has been exercised.

**6.4 · Trusted proxy policy** — starts 6:18 · 16 s · 35 words · 131 wpm

Fourth, the server trusted forwarding headers from anyone, so a client could rewrite its own address and dodge rate limits. Now no proxy is trusted unless it is listed. The real production ingress remains unverified.

**6.5 · Parser resource containment** — starts 6:34 · 18 s · 39 words · 130 wpm

Fifth, a hostile document could tie up a worker. Each parse now runs in a fresh process with time, CPU and memory limits. That is containment, not yet a security sandbox: the child shares the worker's user and network.

**6.6 · Worker recovery and attempt fencing** — starts 6:52 · 18 s · 39 words · 130 wpm

Sixth, a superseded job could resume and publish over newer work. Every claim now carries an attempt number, and stale attempts change nothing. Killed workers were recovered in tests, although with default settings recovery can take about seventeen minutes.

**6.7 · Object storage consistency** — starts 7:10 · 17 s · 37 words · 131 wpm

Seventh, found while fixing that one, a stale crawl could overwrite newer stored pages. Every write now gets a new object key, published only by the attempt that still owns the job, and unpublished uploads are reclaimed.

**6.8 · Pagination and stale state** — starts 7:27 · 18 s · 38 words · 127 wpm

Eighth, the inbox silently dropped older messages, restarted at page one on a bad cursor, and could show stale data. Cursors are now scoped and checked, older messages load on request, and screens reset when the organization changes.

**6.9 · Widget lifecycle and public privacy** — starts 7:45 · 23 s · 51 words · 133 wpm

Ninth, installing the widget twice broke it, nothing could remove it, and visitors could see internal usage fields. A registry now keeps one instance, destroy cleans up, and public responses carry only what the widget needs. The loader is five thousand two hundred and forty-eight bytes compressed. Tested in Chrome only.

**6.10 · Scheduler and maintenance reliability** — starts 8:08 · 18 s · 38 words · 127 wpm

Tenth, recovery shared the busy ingestion workers, and the scheduler's health check did not check scheduling. Recovery now has its own queue and worker, and health means tasks are being accepted. One earlier scheduler crash is still unexplained.

**6.11 · Backup and restore** — starts 8:26 · 17 s · 37 words · 131 wpm

Eleventh, a backup only counts once restored. The rehearsal compared counts, hashes and permissions, and exposed a real defect: the restored database regained delete rights. That is fixed. Off-site copies, alerting and production-sized data are not covered.

### Chapter 7 — Development methodology and testing

**7a · Audit-driven method** — starts 8:43 · 16 s · 34 words · 128 wpm

The method was audit driven. Build the initial system, measure a baseline, record findings, fix one at a time with a failing test first where possible, stabilize performance, then validate the whole thing together.

**7b · The reported results** — starts 8:59 · 20 s · 39 words · 117 wpm

The audit raised seven findings. All seven now pass locally. The reported results: twelve hundred and nine backend tests, seventeen proxy tests run separately, two hundred and sixty-two frontend unit tests, and seventeen browser journeys: fifteen hundred and five.

**7c · Failures and checks on the tests** — starts 9:19 · 17 s · 37 words · 131 wpm

The path was not clean. Earlier checkpoints kept failing tests on record, and a latency gate was missed before it held. To check the tests themselves, fixes were deliberately broken ten times, and each break was caught.

**7d · One hundred concurrent requests** — starts 9:36 · 26 s · 57 words · 132 wpm

At one hundred concurrent chats, sixty-seven succeeded, thirty-three received a controlled rejection and none failed unexpectedly. Successful responses had a ninety-fifth percentile of about one point seven seconds. The gate passed ten of ten declared runs, once with only twenty-five milliseconds to spare. This is an offline provider on one laptop, not real model or server performance.

**7e · Self-audit** — starts 10:02 · 13 s · 28 words · 129 wpm

The self-audit score moved from eighty and a half to eighty-five point seven five. These are local results, not independent certification, and hosted CI has not run yet.

### Chapter 8 — Personal contribution

**8a · Contribution** — starts 10:15 · 36 s · 80 words · 133 wpm

This is my undergraduate portfolio project, built with AI coding assistants including Codex and Claude Code, so I will not claim every line was typed by hand. What I want you to judge is the process: written requirements with explicit acceptance rules, a baseline before changes, an audit, focused fixes with retained failures, and decisions held for approval instead of assumed. Ask me about any trade-off in this video, including the ones that did not work out the first time.

### Chapter 9 — Limitations and future development

**9a · Where it stands** — starts 10:51 · 28 s · 62 words · 133 wpm

Where it stands: the core engineering is validated locally and all seven audit findings pass. One migration policy decision still blocks formal milestone closure. Real AI evaluation, semantic answer quality, hosted CI and production deployment all remain open. Offline retrieval reaches eighty-five percent against a ninety percent target, and the parser is contained, not sandboxed. Those are the roadmap, not existing features.

### Chapter 10 — Closing

**10a · Close** — starts 11:19 · 18 s · 39 words · 130 wpm

A multi-tenant AI customer support platform with retrieval augmented generation. Software engineering, full-stack development and AI engineering. The full case study, with its evidence and its limitations, is on my portfolio at venuja dot online. Thank you for watching.

*Total 11:37; about 11.6 minutes of speech at 130 words per minute.*
