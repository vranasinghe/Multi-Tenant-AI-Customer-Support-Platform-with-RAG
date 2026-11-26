# Narration — the single source for both videos

Facts: [00](00_PROJECT_FACT_CHECK.md). [02](02_CINEMATIC_TRAILER_SCRIPT.md) and
[03](03_FULL_DOCUMENTARY_SCRIPT.md) are the original drafts; 07, 15 and 16 describe the earlier
plan to record a human voice and are superseded.

The voice is AI-generated (Kokoro-82M, voice `af_heart`). After editing, run, from
`tools/portfolio-video`:

    .venv-tts/Scripts/python.exe narration/generate.py

Format: `#### id · title · N s` gives the scene's **design** length, the timeline its visuals were
built on. Each paragraph starts with `(@S)`: the design second of the shot it describes. The
generator lets the real speech set the length and moves each shot to meet its sentence.

## video: showcase

#### A1 · Title · 5 s
> (@0) One platform. Multiple businesses. Customer support grounded in each organization's own
> knowledge.

#### A2 · The product · 14 s
> (@0) This is a multi-tenant AI customer support platform. Each business gets a dashboard,
>
> (@3) a guided chatbot setup,
>
> (@6) a knowledge base,
>
> (@9) an embeddable chat widget,
>
> (@11.5) and a shared team inbox.

#### A3 · Capabilities · 29 s
> (@0) Documents are processed in the background, from queued to ready.
>
> (@5) Answers carry their sources. This demo reply is a fixed sentence, but the retrieval behind
> it is real.
>
> (@10) A second business cannot open this workspace.
>
> (@16) A visitor's conversation survives a page reload.
>
> (@20.5) Analytics come from recorded events,
>
> (@24.5) and installing the widget twice still keeps one.

#### A4 · Architecture · 15 s
> (@0) Underneath are four layers. The experience layer: dashboard and widget.
>
> (@3) The application layer, built on FastAPI.
>
> (@6) Data and background processing.
>
> (@9) And RAG intelligence.
>
> (@12) It is one modular monolith, running as several processes in containers.

#### A5 · Evidence · 19 s
> (@0) The first audit passed five hundred and eighty-two backend tests, and still found problems.
>
> (@5) Today the listed local suites report fifteen hundred and five passing tests.
>
> (@11) All seven audit findings pass locally, and the self-audit score rose from eighty and a half
> to eighty-five point seven five.
>
> (@15) These are local results. Real AI quality and production readiness are unproven.

#### A6 · Close · 6 s
> (@0) Software engineering, full-stack development and AI engineering. The full technical case
> study covers the details. The portfolio address is on screen.

## video: documentary

### chapter 1 — Introduction and business problem

#### 1a · Opening · 21 s
> (@0) What does it take to engineer an AI customer support platform that serves multiple
> businesses,
>
> (@6) while keeping their knowledge,
>
> (@9.5) conversations,
>
> (@13.5) and customer data isolated?
>
> (@17.3) This case study shows the product, the architecture, what broke, and what is unproven.

#### 1b · The business problem · 27 s
> (@0) Customers ask the same questions again and again. The answers usually exist, spread across
> policy documents and web pages, but someone has to find them each time.
>
> (@11) A support assistant grounded in a business's own material can help.
>
> (@19) And if one shared platform serves many separate businesses, every answer has to come from
> the right one, and only that one.

### chapter 2 — Product demonstration

#### 2a · Set up knowledge · 31 s
> (@0) Here is the real application, running locally with fictional data. An owner signs in,
>
> (@4) and lands on the organization dashboard.
>
> (@7) A short wizard creates a chatbot, with its behaviour and appearance.
>
> (@16) Documents are uploaded, and a background worker takes each one from queued, to processing,
> to ready.
>
> (@21) You can inspect the passages it produced,
>
> (@24) and test which ones a question retrieves.
>
> (@28) Websites can be added too. Here, the crawler refuses a private network address.

#### 2b · Ask a question · 21 s
> (@0) In the playground, a question streams back with a numbered source. One important note: this
> is a deterministic demonstration. The reply is a fixed sentence, not an AI answer. What is real
> is the retrieval, the streaming and the citation.
>
> (@14) An unrelated question gets a fallback instead.

#### 2c · Customers and the team · 19 s
> (@0) Once the bot is active, the website's origin is verified.
>
> (@4) A visitor asks through the embedded widget, and the conversation is stored.
>
> (@11) The team sees it in the inbox and marks it resolved.
>
> (@16) Analytics update from stored events. These figures are synthetic demonstration data.

### chapter 3 — System architecture

#### 3a · Experience layer · 19 s
> (@0) The system is a modular monolith: one Python codebase and one database, run as several
> processes. Think of it in four layers.
>
> (@4) First, experience. A dashboard built with Next.js, React and TypeScript, and a small widget
> that opens an isolated frame on a customer's site.

#### 3b · Application layer · 13 s
> (@0) Second, the application. FastAPI handles ordinary requests. Dashboard requests are
> authenticated and checked against the member's role, and chat answers stream back as
> server-sent events.

#### 3c · Data and processing layer · 18 s
> (@0) Third, data and processing. PostgreSQL holds relational data, and vectors with pgvector.
> Private object storage keeps the original files. Redis carries the queue to Celery workers, and
> Celery Beat schedules a recovery sweep for a separate maintenance worker.

#### 3d · Intelligence layer · 12 s
> (@0) Fourth, intelligence: document processing, retrieval and prompt construction, with adapters
> for language and embedding models. This is code inside those same processes, not separate
> services.

#### 3e · The whole system · 12 s
> (@0) Together: synchronous requests, streamed answers, and background jobs, in Docker
> containers.
>
> (@6) Several containers do not make this microservices. This detailed diagram shows each
> connection.

### chapter 4 — The retrieval pipeline

#### 4a · From file to vectors · 20 s
> (@0) Retrieval augmented generation, or RAG, means finding evidence first, then writing from
> it. A file or web page is extracted into text and cleaned.
>
> (@10) It is split into overlapping chunks that never cross a heading. Each chunk gets an
> embedding, a list of numbers, stored beside the text.

#### 4b · Search and citations · 25 s
> (@0) A question is searched two ways. Vector search compares embeddings, keyword search matches
> words, and the two rankings are merged. Retrieval is always scoped to one organization and one
> chatbot.
>
> (@15) The prompt is assembled, the model streams, and citations are validated on the way out.
> Only sources that actually entered the prompt can be cited.

#### 4c · What is not established · 21 s
> (@0) Citation provenance establishes which sources were shown to the model. It does not show
> that a source supports the sentence.
>
> (@7.7) Offline answer-bearing recall at five is eighty-five percent, measured with stand-in
> embeddings that only match words. The target is ninety percent. Real model accuracy is
> untested.

### chapter 5 — Multi-tenant security

#### 5a · Two businesses · 13 s
> (@0) Take two fictional businesses, each with its own chatbot, documents and conversations.
>
> (@4.5) Here the second owner opens the first one's address, and gets organization not found.

#### 5b · The layers · 21 s
> (@0) Several layers enforce this. Sessions are managed on the server. The browser holds only an
> opaque session identifier, in an HttpOnly cookie. Roles decide what each member may do. Queries
> are scoped to the organization, and PostgreSQL enforces forced row-level security underneath, so
> a missed filter is not enough to leak a row.

#### 5c · Public boundaries · 18 s
> (@0) Public widgets receive short-lived tokens limited to one conversation, and visitors get
> only the fields they need. Forwarding headers are trusted only from listed proxies, and AI
> providers must use HTTPS.
>
> (@11) This is tested design, not a security certification, and not every attack has been tried.

### chapter 6 — Engineering problems and solutions

#### 6.0 · Eleven problems · 13 s
> (@0) An audit then found problems that the existing, passing tests had missed. Here are eleven,
> some from the audit and some found while fixing it.

#### 6.1 · Connection pool starvation · 19 s
> (@0.4) First. Ten simultaneous chats all failed.
>
> (@3.2) Each request held one database connection while asking for another.
>
> (@6.5) The fix releases it early, keeps transactions short, admits only bounded work, and makes
> cleanup safe to repeat.
>
> (@10.5) At one hundred concurrent requests, sixty-seven succeeded, thirty-three received a
> controlled rejection, and there were zero unexpected failures.
>
> (@14.3) That used an offline provider on one laptop.

#### 6.2 · Citation provenance · 19 s
> (@0.4) Second. A source cut from the prompt could still be cited.
>
> (@3.2) Citations were checked against what was selected, not what was shown.
>
> (@6.5) Now one renderer records exactly which sources the model saw, even while streaming.
>
> (@10.5) The original failing test passes, with thirty-two new tests.
>
> (@14.3) Whether a source supports a sentence is still unverified.

#### 6.3 · Provider transport security · 16 s
> (@0.3) Third. Production settings accepted a plain HTTP embedding endpoint.
>
> (@2.7) No transport rule covered provider addresses, so keys and documents could travel
> unencrypted.
>
> (@5.4) Providers now require HTTPS with certificate verification, refuse redirects, and ignore
> environment proxies.
>
> (@8.8) One hundred and fifty-nine new transport tests pass.
>
> (@12) No real external provider has been exercised.

#### 6.4 · Trusted proxy policy · 16 s
> (@0.3) Fourth. A client could rewrite its own address and avoid rate limits.
>
> (@2.7) The server trusted forwarding headers from every peer.
>
> (@5.4) Now no proxy is trusted unless it is explicitly listed.
>
> (@8.8) One hundred and ninety-seven unit cases and seventeen runtime checks pass.
>
> (@12) The real production ingress remains unverified.

#### 6.5 · Parser resource containment · 18 s
> (@0.4) Fifth. A hostile document could tie up a worker.
>
> (@3) Parsing ran inside the long-lived worker, with no limits.
>
> (@6.1) Each parse now runs in a fresh process with limits on time, processor, memory and output.
>
> (@9.9) One hundred new tests pass, including killed and restarted workers.
>
> (@13.5) This is containment, not a complete security sandbox.

#### 6.6 · Worker recovery and attempt fencing · 18 s
> (@0.4) Sixth. A superseded job could resume and publish over newer work.
>
> (@3) A claim did not say which attempt owned the job.
>
> (@6.1) Every claim now carries an attempt number, and stale attempts change nothing.
>
> (@9.9) Killed workers recovered in about thirty seconds, using shortened test intervals.
>
> (@13.5) With default settings, recovery can take about seventeen minutes.

#### 6.7 · Object storage consistency · 17 s
> (@0.4) Seventh, found while fixing that one. A stale crawl could overwrite newer stored pages.
>
> (@2.9) Each page had one fixed storage key.
>
> (@5.8) Every write now gets a new key, published only by the attempt that still owns the job.
> Unused uploads are reclaimed.
>
> (@9.4) Thirteen of twenty new tests failed before the fix. All twenty pass now.
>
> (@12.8) It was tested on local object storage only.

#### 6.8 · Pagination and stale state · 18 s
> (@0.4) Eighth. The inbox silently dropped older messages, and a bad cursor returned page one.
>
> (@3) Cursors were unchecked, and screen state survived an organization switch.
>
> (@6.1) Cursors are now scoped and validated, older messages load on request, and screens reset
> safely.
>
> (@9.9) Twenty-six new backend tests pass.
>
> (@13.5) Pages are not a snapshot: a busy conversation can be missed until refresh.

#### 6.9 · Widget lifecycle and public privacy · 23 s
> (@0.5) Ninth. Installing the widget twice broke it, nothing could remove it, and visitors could
> see internal usage fields.
>
> (@3.9) There was no instance registry, and the dashboard response shape was reused.
>
> (@7.8) A registry now keeps one instance, destroy cleans up, conversations resume, and public
> responses are allow-listed.
>
> (@12.7) The compressed loader is five thousand two hundred and forty-eight bytes, against a
> budget of ten thousand two hundred and forty.
>
> (@17.3) It was tested in Chrome only.

#### 6.10 · Scheduler and maintenance reliability · 18 s
> (@0.4) Tenth. Recovery shared the busy ingestion workers.
>
> (@3) And a healthy scheduler only meant that a process was running.
>
> (@6.1) Recovery now has its own queue and worker, and health means tasks are being accepted.
>
> (@9.9) With every ingestion slot busy, recovery still ran in under two seconds, at a test
> interval.
>
> (@13.5) One earlier scheduler crash remains unexplained.

#### 6.11 · Backup and restore · 17 s
> (@0.4) Eleventh. A backup only counts once it has been restored.
>
> (@2.9) The rehearsal found the restored database had regained delete rights.
>
> (@5.8) That is fixed, and restore compares data fingerprints, counts and permissions.
>
> (@9.4) The local rehearsal passed.
>
> (@12.8) Off-site copies, alerting and production-scale recovery are not validated.

### chapter 7 — Development methodology and testing

#### 7a · Audit-driven method · 16 s
> (@0) The method was audit driven: build, measure a baseline, record findings, and fix one at a
> time, with a failing test first where possible.
>
> (@6.7) Seven findings were remediated, with stabilization checkpoints between them.

#### 7b · The reported results · 20 s
> (@0) The first audit passed five hundred and eighty-two backend tests, yet its added checks
> failed. All seven findings now pass locally.
>
> (@11.7) The listed suites report twelve hundred and nine backend tests, seventeen proxy tests
> run separately, two hundred and sixty-two frontend unit tests, and seventeen browser journeys:
> fifteen hundred and five.

#### 7c · Failures and checks on the tests · 17 s
> (@0) The path was not clean. Earlier checkpoints kept failing tests on record, and a latency
> gate was missed before it held.
>
> (@9.7) To check the tests themselves, fixes were deliberately broken ten times, and each break
> was caught.

#### 7d · One hundred concurrent requests · 26 s
> (@0) At one hundred concurrent chats, sixty-seven succeeded. Thirty-three received a controlled
> rejection, which is not an answer. None failed unexpectedly. Successful responses had a P95 of
> about sixteen hundred and eighty-two milliseconds.
>
> (@17.7) The gate passed ten of ten declared runs, once with only twenty-five milliseconds to
> spare. This is not real model or server performance.

#### 7e · Self-audit · 13 s
> (@0) The self-audit score moved from eighty and a half to eighty-five point seven five. It is
> not independent certification.
>
> (@8.3) Hosted CI is configured, but has not been run.

### chapter 8 — Development process

#### 8a · How it was built · 30 s
> (@0) This undergraduate portfolio project was developed with AI coding assistants, including
> Codex and Claude Code.
>
> (@5) Its development process used written requirements, explicit acceptance criteria, baseline
> measurements, focused remediation and documented validation.
>
> (@20) Failures were kept on record, and decisions needing approval were held, not assumed.

### chapter 9 — Limitations and future development

#### 9a · Where it stands · 28 s
> (@0) Where it stands: the core engineering is validated locally, and all seven audit findings
> pass. A migration recovery policy still awaits approval.
>
> (@11) Real AI evaluation, semantic retrieval quality and answer correctness are untested. Hosted
> CI and production deployment remain open. The parser is not sandboxed, and production backup and
> monitoring are unfinished. These are requirements still to meet.

### chapter 10 — Closing

#### 10a · Close · 18 s
> (@0) A multi-tenant AI customer support platform with retrieval augmented generation.
>
> (@5.3) Its value is in the engineering: isolation, failure handling and evidence you can check.
>
> (@13.5) Thank you for watching. The portfolio address is on screen.
