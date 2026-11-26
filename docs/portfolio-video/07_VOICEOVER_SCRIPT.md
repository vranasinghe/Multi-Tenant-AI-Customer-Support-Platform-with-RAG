# Voice-over script (superseded)

**Superseded** for the revised videos by [16_VOICEOVER_SCRIPT.md](16_VOICEOVER_SCRIPT.md). This copy matches the original 80-second preview only.

Generated from the video scripts by `subtitles/build.py`. **Do not edit here.**

How to read it: quiet room, 15–20 cm from the microphone, one scene per take, a second of
silence before and after. Target 120–145 words per minute; pause at blank lines. The
rate below counts written words: spoken numbers run longer, so check scene 09 aloud.

Say: *pgvector* “P-G vector” · *FastAPI* “fast A-P-I” · *Celery* “SELL-uh-ree” ·
*Redis* “RED-iss” · *RBAC* “R-back” · *venuja.online* “venuja dot online”.

## Video A — showcase

### A1 · Hook · 0:00 · 10 s · 21 words · 126 wpm

One platform serving many businesses. Each brings its own documents, customers and conversations, and none of that should ever cross over.

### A2 · The product · 0:10 · 13 s · 26 words · 120 wpm

This is a multi-tenant AI customer support platform. A business adds its documents and website, sets up a chatbot, and embeds it on its own site.

### A3 · It works · 0:23 · 20 s · 38 words · 114 wpm

Answers stream back with their sources, and every conversation reaches a team inbox. This recording uses an offline demo model, so the reply is a fixed sentence. The retrieval, the streaming and the citation behind it are real.

### A4 · Underneath · 0:43 · 14 s · 28 words · 120 wpm

Underneath is a Next.js dashboard, a FastAPI backend, PostgreSQL with vector search, and Redis driving background workers. It is one modular monolith, running as several processes in containers.

### A5 · Evidence · 0:57 · 15 s · 29 words · 116 wpm

An audit found seven problems. All seven now have passing local evidence, backed by fifteen hundred and five passing tests. Real AI quality and production readiness are still unproven.

### A6 · Close · 1:12 · 8 s · 16 words · 120 wpm

Software engineering, full-stack development and applied AI. Read the full case study at venuja dot online.

*158 words over 80 s.*

## Video B — documentary

### 01 · Opening · 0:00 · 25 s · 46 words · 110 wpm

What does it take to engineer an AI customer support platform that can serve multiple businesses while keeping their knowledge, conversations, and customer data isolated?

This case study shows the working product, the architecture behind it, what broke along the way, and what is still unproven.

### 02 · The problem · 0:25 · 30 s · 60 words · 120 wpm

Customers ask the same questions again and again. The answers usually exist, spread across policy documents and web pages, but someone has to find them each time. A support assistant grounded in a business's own material can help. And if one shared platform serves many separate businesses, every answer has to come from the right one, and only that one.

### 03 · Product walkthrough · 0:55 · 75 s · 151 words · 121 wpm

Here is the real application, running locally with fictional data. An owner signs in and lands on the organization dashboard. A short wizard creates a chatbot. Documents are uploaded, and a background worker takes each one from queued, to processing, to ready. You can inspect the passages it produced and test which ones a question retrieves. Websites can be added too; here the crawler refuses a private network address.

In the playground, a question streams back with a numbered source. One important note: this is a deterministic demonstration. The reply is a fixed sentence, not an AI answer. What is real is the retrieval, the streaming and the citation. An unrelated question gets a fallback instead.

Once the bot is active and the website's origin is verified, a visitor asks through the embedded widget. The team sees that conversation in the inbox, marks it resolved, and analytics update from stored events.

### 04 · Architecture · 2:10 · 70 s · 144 words · 123 wpm

The system is a modular monolith: one Python codebase and one database, run as several processes. That is not microservices, even though there are several containers.

The Next.js and React dashboard talks to a FastAPI backend over ordinary requests. Dashboard requests are authenticated and checked against the member's role. Chat answers come back from the same API as a stream of server-sent events. The widget on a customer's site is a small loader that opens an isolated frame.

PostgreSQL holds relational data and vectors, using the pgvector extension. Private object storage keeps the original files. Language and embedding models sit behind provider adapters.

Slow work leaves the request path. Redis carries the queue to Celery workers, which parse, chunk and embed documents. A scheduler triggers a recovery sweep on its own maintenance worker, so busy ingestion cannot delay it. Everything runs in Docker containers.

### 05 · The retrieval pipeline · 3:20 · 60 s · 134 words · 134 wpm

Retrieval augmented generation means finding evidence first, then writing from it. A file or web page is extracted into text, cleaned, and split into overlapping chunks that never cross a heading. Each chunk gets an embedding, a list of numbers, stored beside the text.

A question is searched two ways: vector search compares embeddings, keyword search matches words, and the two rankings are merged. Retrieval is always scoped to one organization and one chatbot. The prompt is assembled, the model streams, and citations are validated on the way out.

Citation provenance proves a source was shown to the model, not that it supports the sentence. Offline, with a word-matching stand-in for embeddings, the answer appeared in the top five for eighty-five percent of cases, below the ninety percent target. Real model accuracy is untested.

### 06 · Keeping businesses apart · 4:20 · 55 s · 111 words · 121 wpm

Take two fictional businesses. Each has its own chatbot, documents and conversations. Here the second owner opens the first one's address, and gets organization not found.

Several layers enforce this. Sessions live on the server, in a cookie scripts cannot read. Roles decide what each member may do. Queries are scoped to the organization, and PostgreSQL enforces forced row-level security underneath, so a missed filter is not enough to leak a row.

Public widgets receive short-lived tokens limited to one conversation, and visitors get only the fields they need. Forwarding headers are trusted only from listed proxies, and AI providers must use HTTPS. This is tested design, not a security certification.

### 07 · What broke, and how it was fixed · 5:15 · 75 s · 155 words · 124 wpm

An audit then found problems that the existing, passing tests had missed.

First, ten simultaneous chats exhausted the database connection pool. Each request held one connection while asking for another. The fix releases it early, keeps transactions short, and queues or refuses extra work. At one hundred concurrent requests, sixty-seven were served, thirty-three were politely refused, and none failed.

Second, a source cut from the prompt could still be cited. Now only sources actually rendered can be cited, even midway through a stream.

Third, a hostile document could tie up a worker. Each parse now runs in a fresh process with time and memory limits, and a failed attempt leaves the previous version in place. That is containment, not yet a security sandbox.

Fourth, found while fixing that one, a stale crawl could overwrite newer stored pages. Every write now gets a new object key, published only by the attempt that still owns the job.

### 08 · The widget · 6:30 · 45 s · 90 words · 120 wpm

The widget has to behave on websites it does not control. Adding the same script twice keeps one instance. A second instance must be asked for. Destroying it removes the frame and its listener, so single-page applications can remount safely. An anonymous visitor's conversation resumes after a reload, and an interrupted answer is recorded as interrupted. It adapts to a phone screen. The loader is five thousand two hundred and forty-eight bytes compressed, against a budget of ten thousand two hundred and forty. These journeys were tested in Chrome only.

### 09 · How it was validated · 7:15 · 75 s · 155 words · 124 wpm

The method was audit driven. Build the initial system, measure a baseline, record findings, fix one at a time with a failing test first where possible, stabilize performance, then validate the whole thing together.

The audit raised seven findings, from the connection pool to the widget. All seven now pass locally. The reported results: twelve hundred and nine backend tests, seventeen proxy tests run separately, two hundred and sixty-two frontend unit tests, and seventeen browser journeys. That is fifteen hundred and five.

To check the tests themselves, fixes were deliberately broken ten times, and each break was caught. The capacity gate passed ten of ten declared runs, once with only twenty-five milliseconds to spare. A backup and restore rehearsal passed, and exposed a permissions bug, now fixed.

The self-audit score moved from eighty and a half to eighty-five point seven five. These are local results, not independent certification, and hosted CI has not run yet.

### 10 · My contribution · 8:30 · 40 s · 80 words · 120 wpm

This is my undergraduate portfolio project, built with AI coding assistants including Codex and Claude Code, so I will not claim every line was typed by hand. What I want you to judge is the process: written requirements with explicit acceptance rules, a baseline before changes, an audit, focused fixes with retained failures, and decisions held for approval instead of assumed. Ask me about any trade-off in this video, including the ones that did not work out the first time.

### 11 · Honest status and next steps · 9:10 · 30 s · 60 words · 120 wpm

Where it stands: the core engineering is validated locally and all seven audit findings pass. One migration policy decision still blocks formal milestone closure. Real AI evaluation, semantic answer quality, hosted CI and production deployment all remain open. Those are the roadmap, not existing features, which is why you are watching a controlled demonstration rather than an always-on public service.

### 12 · Close · 9:40 · 20 s · 39 words · 117 wpm

A multi-tenant AI customer support platform with retrieval augmented generation. Software engineering, full-stack development and AI engineering. The full case study, with its evidence and its limitations, is on my portfolio at venuja dot online. Thank you for watching.

*1225 words over 600 s.*
