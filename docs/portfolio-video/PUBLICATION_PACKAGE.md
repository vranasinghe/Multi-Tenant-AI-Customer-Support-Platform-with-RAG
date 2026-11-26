# Publication package

**Nothing here has been published.** Complete the human review in
[FINAL_VIDEO_QA_REPORT.md](FINAL_VIDEO_QA_REPORT.md) first.

## Files

All in `output/video/final/` (gitignored).

| Use | File |
|---|---|
| YouTube documentary | `documentary-final.mp4` + upload `documentary-final.en.srt` |
| Portfolio showcase | `showcase-final.mp4` + `showcase-final.en.vtt` |
| Social or muted autoplay | `showcase-final-captioned.mp4`, `documentary-final-captioned.mp4` |
| Thumbnail | `thumbnail-1280x720.png` (editable: `.svg`) |
| Portfolio cover | `portfolio-cover-1920x1080.png` (editable: `.svg`) |

## YouTube

**Title**

> Beyond a Chatbot — Engineering a Multi-Tenant AI Customer Support Platform

**Description**

```
An engineering case study of an undergraduate portfolio project: a multi-tenant AI customer
support platform that answers from each business's own documents and websites.

Covered: the working product, architecture, the retrieval pipeline, tenant isolation, eleven
engineering problems with their root causes and fixes, testing, and what is still unproven.

Stack: Next.js, React, TypeScript, FastAPI, Python, PostgreSQL + pgvector, Redis, Celery,
S3-compatible storage, Docker.

About the demonstration: it runs locally with fictional data, a deterministic "demo" model that
returns a fixed sentence, and word-matching "hash" embeddings. It does not show real AI answer
quality. Results are local validation, not independent certification. Hosted CI has not run and
the platform is not deployed to production.

Narration is AI-generated (Kokoro-82M, a stock synthetic voice). It is not the developer's voice.
The project was developed with AI coding assistants. Background music is original, synthesised
for this video.

Portfolio: https://venuja.online

Chapters
0:00 Introduction and business problem
0:44 Product demonstration
2:00 System architecture
3:22 The retrieval pipeline
4:28 Multi-tenant security
5:27 Eleven engineering problems
5:38 Connection pool starvation
6:06 Citation provenance
6:27 Provider transport security
6:55 Trusted proxy policy
7:16 Parser resource containment
7:38 Worker recovery and attempt fencing
7:59 Object storage consistency
8:24 Pagination and stale state
8:49 Widget lifecycle and public privacy
9:20 Scheduler and maintenance reliability
9:43 Backup and restore
10:04 Development methodology and testing
11:40 How it was built
12:06 Limitations and future development
12:36 Closing
```

**Tags:** `rag`, `multi-tenant`, `saas`, `fastapi`, `nextjs`, `postgresql`, `pgvector`, `celery`,
`row-level security`, `system design`, `software engineering portfolio`

**Settings:** category Science & Technology; language English; upload as **Unlisted** first. For
the "altered or synthetic content" question, check YouTube's current rule and declare the synthetic
narration if it applies.

## Portfolio project card

**Multi-Tenant AI Customer Support Platform with RAG**

Support chatbots that answer from each business's own documents, with tenant data kept apart by
role checks and forced row-level security. Background ingestion, hybrid retrieval with traceable
citations, and an embeddable widget. Seven audit findings fixed and validated locally; 1,505 tests
passing across the listed local suites. Undergraduate portfolio project, not a production service.

`Full-stack` · `Backend` · `RAG` · `Multi-tenancy` · `PostgreSQL`

## Detailed case study

[11_PORTFOLIO_CASE_STUDY.md](11_PORTFOLIO_CASE_STUDY.md) holds the long text. Before using it:
replace the `[…]` placeholders, use the neutral contribution wording below, change the video
lengths to 1:40 and 12:54, and leave out the repository line.

> This undergraduate portfolio project was developed with AI coding assistants, including Codex
> and Claude Code. Its development process used written requirements, explicit acceptance criteria,
> baseline measurements, focused remediation and documented validation.

## Embed snippet

Host the files next to the page; adjust the paths.

```html
<video controls preload="metadata" playsinline width="1920" height="1080"
       style="width:100%;height:auto;background:#080C14"
       poster="/media/portfolio-cover-1920x1080.png">
  <source src="/media/showcase-final.mp4" type="video/mp4" />
  <track kind="captions" srclang="en" label="English" src="/media/showcase-final.en.vtt" default />
  <a href="/media/showcase-final.mp4">Download the video</a>
</video>
<p>Local demonstration with fictional data. Narration is AI-generated.</p>
```

## Repository link

Left out on purpose. The public default branch holds only the first commit; the work these videos
describe is not committed or pushed. Add the link after the reviewed code is public.
