"""Generate the editable SVG diagrams and overlay assets for the portfolio videos.

    python docs/portfolio-video/diagrams/build_diagrams.py

Every shape and label is plain SVG, editable in Figma, Inkscape or After Effects. Groups named
``step-N`` are the animation layers, revealed in order. Measured figures carry their source in the
footnote; change a number only when the cited artifact changes.
"""

from __future__ import annotations

import pathlib
from html import escape

HERE = pathlib.Path(__file__).parent
ASSETS = HERE.parent / "assets"

BG, SURFACE, BLUE, ACCENT = "#080C14", "#111827", "#2563EB", "#38BDF8"
WHITE, MUTED, GREEN, AMBER, RED = "#FFFFFF", "#94A3B8", "#22C55E", "#F59E0B", "#EF4444"
LINE = "#1F2A3D"
SANS = "Inter, 'Plus Jakarta Sans', 'Segoe UI', sans-serif"
MONO = "'JetBrains Mono', Consolas, monospace"

# line kinds: colour, dash pattern, legend label
KINDS = {
    "sync": (BLUE, "", "Synchronous request"),
    "sse": (ACCENT, "2 10", "SSE stream"),
    "job": (MUTED, "14 10", "Background job"),
    "db": (WHITE, "", "Database transaction"),
    "obj": ("#A78BFA", "", "Private object storage"),
    "ai": (ACCENT, "22 8 4 8", "AI provider request"),
    "ok": (GREEN, "", "Verified"),
    "warn": (AMBER, "14 10", "Controlled rejection"),
    "bad": (RED, "", "Failure"),
}


def text(x, y, value, size=22, colour=WHITE, weight=400, anchor="start", mono=False, extra=""):
    return (
        f'<text x="{x}" y="{y}" font-family="{MONO if mono else SANS}" font-size="{size}" '
        f'font-weight="{weight}" fill="{colour}" text-anchor="{anchor}" {extra}>'
        f"{escape(str(value))}</text>"
    )


def rect(x, y, w, h, fill=SURFACE, stroke=LINE, radius=16, width=2, dash=""):
    dashed = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{width}"{dashed}/>'
    )


def node(x, y, w, h, title, lines=(), stroke=LINE, title_size=26, size=19, dash=""):
    """A card with a centred title and detail lines."""
    parts = [rect(x, y, w, h, stroke=stroke, dash=dash)]
    block = title_size + len(lines) * (size + 10)
    top = y + (h - block) / 2 + title_size - 4
    parts.append(text(x + w / 2, top, title, title_size, WHITE, 700, "middle"))
    for i, line in enumerate(lines):
        parts.append(text(x + w / 2, top + (i + 1) * (size + 10), line, size, MUTED, 400, "middle"))
    return "".join(parts)


def arrow(points, kind="sync", label="", at=None, width=3.5):
    colour, dash, _ = KINDS[kind]
    path = "M " + " L ".join(f"{x} {y}" for x, y in points)
    dashed = f' stroke-dasharray="{dash}"' if dash else ""
    out = (
        f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"{dashed} marker-end="url(#m-{kind})"/>'
    )
    if label:
        lx, ly = at or ((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2 - 10)
        out += text(lx, ly, label, 17, colour if kind != "db" else MUTED, 500, "middle",
                    extra=f'paint-order="stroke" stroke="{BG}" stroke-width="6"')
    return out


def step(n, *parts):
    return f'<g id="step-{n}">{"".join(parts)}</g>'


def legend(kinds, x=96, y=1000):
    out = []
    for kind in kinds:
        colour, dash, label = KINDS[kind]
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(
            f'<line x1="{x}" y1="{y}" x2="{x + 56}" y2="{y}" stroke="{colour}" '
            f'stroke-width="4" stroke-linecap="round"{dashed}/>'
        )
        out.append(text(x + 70, y + 6, label, 17, MUTED))
        x += 100 + len(label) * 9
    return f'<g id="legend">{"".join(out)}</g>'


def badge(kind):
    label, colour = {
        "measured": ("MEASURED · LOCAL", GREEN),
        "illustrative": ("ILLUSTRATIVE", AMBER),
        "code": ("FROM SOURCE CODE", ACCENT),
        "plan": ("PLANNED · NOT BUILT", AMBER),
    }[kind]
    w = len(label) * 12 + 40
    return (
        rect(1824 - w, 62, w, 40, fill=BG, stroke=colour, radius=20)
        + text(1824 - w / 2, 89, label, 17, colour, 700, "middle", extra='letter-spacing="1"')
    )


def svg(name, title, subtitle, kind, body, footnote):
    markers = "".join(
        f'<marker id="m-{k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{v[0]}"/>'
        "</marker>"
        for k, v in KINDS.items()
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" '
        'viewBox="0 0 1920 1080">\n'
        f"<title>{escape(title)}</title>\n<defs>{markers}</defs>\n"
        f'<rect width="1920" height="1080" fill="{BG}"/>\n'
        f'<g id="heading">{text(96, 100, title, 46, WHITE, 700)}'
        f"{text(96, 142, subtitle, 22, MUTED)}{badge(kind)}</g>\n"
        f"{body}\n"
        f'<g id="footnote">{text(96, 1050, footnote, 15, MUTED)}</g>\n</svg>\n'
    )
    (HERE / name).write_text(document, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- D01 architecture
def d01():
    body = "".join([
        step(1,
             node(96, 250, 300, 130, "Business dashboard", ("Browser · signed-in member",)),
             node(96, 620, 300, 150, "Customer website", ("Widget loader", "+ isolated iframe"))),
        step(2,
             node(580, 200, 340, 130, "web", ("Next.js · React · TypeScript",), BLUE),
             node(580, 420, 340, 330, "api · FastAPI", (
                 "Session auth + role checks", "Chat (SSE)", "Knowledge + retrieval",
                 "Inbox + analytics", "Public widget routes"), BLUE),
             arrow([(396, 285), (580, 265)], "sync", "pages", (480, 250)),
             arrow([(396, 345), (500, 345), (500, 460), (580, 460)], "sync", "REST + cookie", (480, 420)),
             arrow([(396, 665), (580, 625)], "sync", "scoped token", (480, 628)),
             arrow([(580, 690), (396, 730)], "sse", "answer stream", (488, 742))),
        step(3,
             node(1090, 200, 320, 160, "PostgreSQL 18", ("pgvector · full-text", "FORCE row-level security")),
             node(1090, 470, 320, 130, "Redis", ("queues · rate limits · leases",)),
             node(1090, 690, 320, 130, "Object storage", ("private · S3 API",)),
             arrow([(920, 440), (1000, 440), (1000, 290), (1090, 290)], "db", "transactions", (1000, 270)),
             arrow([(920, 540), (1090, 540)], "sync", "limits + enqueue", (1005, 528)),
             arrow([(920, 640), (1000, 640), (1000, 740), (1090, 740)], "obj", "originals", (1004, 768))),
        step(4,
             node(1520, 300, 304, 170, "worker · Celery", ("ingest · crawl · default", "2 slots", "parser child process")),
             node(1520, 540, 304, 120, "maintenance", ("recovery sweep · 1 slot",)),
             node(1520, 730, 304, 120, "beat", ("scheduler · exactly one",)),
             arrow([(1410, 505), (1460, 505), (1460, 385), (1520, 385)], "job", "jobs", (1462, 372)),
             arrow([(1410, 550), (1470, 550), (1470, 600), (1520, 600)], "job"),
             arrow([(1520, 790), (1440, 790), (1440, 580), (1410, 580)], "job", "schedule", (1455, 815)),
             arrow([(1520, 330), (1470, 330), (1470, 250), (1410, 250)], "db"),
             arrow([(1672, 470), (1672, 505), (1480, 505), (1480, 710), (1410, 710)], "obj")),
        step(5,
             node(580, 850, 340, 100, "Provider adapters", ("LLM + embeddings · HTTPS",), ACCENT),
             arrow([(750, 750), (750, 850)], "ai"),
             arrow([(1824, 385), (1860, 385), (1860, 920), (920, 920)], "ai", "embeddings", (1390, 908))),
        legend(["sync", "sse", "job", "db", "obj", "ai"]),
    ])
    svg("D01-architecture.svg", "Application architecture",
        "A modular monolith: one codebase and one database, run as several Docker containers",
        "code", body,
        "Source: docker-compose.yml, app/workers/celery_app.py. Maintenance also uses the database and storage. "
        "Validation used offline providers; no real AI provider has been run.")


# ---------------------------------------------------------------- D02 tenant isolation
def d02():
    def org(x, name, bot, colour):
        return "".join([
            rect(x, 190, 560, 240, stroke=colour),
            text(x + 280, 235, name, 28, WHITE, 700, "middle"),
            node(x + 24, 265, 160, 135, "Chatbot", (bot,), title_size=21, size=15),
            node(x + 200, 265, 160, 135, "Documents", ("own chunks", "own originals"), title_size=21, size=15),
            node(x + 376, 265, 160, 135, "Conversations", ("own history",), title_size=19, size=15),
        ])

    layers = [
        ("1 · Server-side session", "who is asking"),
        ("2 · Membership and role", "owner · admin · agent · viewer — non-members get 404"),
        ("3 · Organization-scoped queries", "org id in every statement and storage key"),
        ("4 · PostgreSQL FORCE row-level security", "runtime role cannot bypass it"),
    ]
    rows = []
    for i, (title, detail) in enumerate(layers):
        y = 470 + i * 92
        rows.append(step(i + 2,
                         rect(420, y, 1080, 74, stroke=BLUE),
                         text(450, y + 45, title, 23, WHITE, 700),
                         text(1470, y + 45, detail, 18, MUTED, anchor="end")))
    body = "".join([
        step(1, org(96, "Northwind Outdoor", "fictional", BLUE), org(1264, "Bluepeak Fitness", "fictional", ACCENT)),
        *rows,
        step(6,
             node(420, 850, 520, 90, "Northwind rows", ("visible to Northwind only",), BLUE, 22, 16),
             node(980, 850, 520, 90, "Bluepeak rows", ("visible to Bluepeak only",), ACCENT, 22, 16)),
        step(7,
             arrow([(1544, 430), (1544, 599), (1500, 599)], "bad"),
             text(1560, 640, "Bluepeak owner asks", 19, RED, 700),
             text(1560, 668, "for Northwind data", 19, RED, 700),
             text(1560, 706, "404 · stops at layer 2", 19, MUTED)),
    ])
    svg("D02-tenant-isolation.svg", "Multi-tenant isolation",
        "One shared platform, independent layers that each keep organizations apart",
        "code", body,
        "Source: app/api/deps.py, app/services/tenancy/policy.py, app/core/rls.py. The 404 was reproduced "
        "while recording (R14). Not a security certification.")


# ---------------------------------------------------------------- D03 RAG pipeline
def d03():
    def row(y, items, start):
        out = []
        for i, (title, detail) in enumerate(items):
            x = 96 + i * 292
            parts = [node(x, y, 252, 140, title, detail, BLUE, 22, 16)]
            if i:
                parts.append(arrow([(x - 40, y + 70), (x - 4, y + 70)], "sync"))
            out.append(step(start + i, *parts))
        return "".join(out)

    top = [("Upload or crawl", ("get the source",)), ("Extract", ("file → text blocks",)),
           ("Clean", ("NFKC · de-duplicate",)), ("Chunk", ("~350 tokens", "50 overlap")),
           ("Embed", ("text → 1536 numbers",)), ("Store", ("pgvector + full-text",))]
    bottom = [("Question", ("one org, one bot",)), ("Retrieve", ("vector + keyword",)),
              ("Assemble prompt", ("only what fits",)), ("Generate", ("model streams",)),
              ("Validate citations", ("rendered sources only",)), ("Stream answer", ("SSE to the browser",))]
    body = "".join([
        text(96, 220, "INGESTION · background", 18, ACCENT, 700),
        row(240, top, 1),
        text(96, 480, "ANSWERING · request", 18, ACCENT, 700),
        row(500, bottom, 7),
        step(13,
             arrow([(514, 640), (514, 700), (300, 700), (300, 740)], "sync"),
             arrow([(514, 640), (514, 700), (728, 700), (728, 740)], "sync"),
             node(150, 750, 300, 110, "Vector search", ("closeness of embeddings",), ACCENT, 21, 16),
             node(578, 750, 300, 110, "Keyword search", ("matching words",), ACCENT, 21, 16),
             node(364, 885, 300, 80, "Rank fusion (k = 60)", (), BLUE, 21),
             arrow([(300, 860), (300, 925), (364, 925)], "sync"),
             arrow([(728, 860), (728, 925), (664, 925)], "sync")),
        step(14,
             rect(1000, 730, 824, 235, stroke=AMBER),
             text(1030, 775, "What is and is not established", 24, AMBER, 700),
             text(1030, 815, "Answer-bearing Recall@5: 85% (68/80) against a 90% target", 19, WHITE),
             text(1030, 847, "Offline hash baseline: matches words, has no semantic knowledge", 19, MUTED),
             text(1030, 879, "Citation provenance: enforced (the source was shown to the model)", 19, GREEN),
             text(1030, 911, "Semantic citation correctness: unverified", 19, AMBER),
             text(1030, 943, "Real-model accuracy and faithfulness: not measured", 19, AMBER)),
    ])
    svg("D03-rag-pipeline.svg", "Retrieval augmented generation pipeline",
        "Find evidence first, then write from it", "code", body,
        "Source: app/rag/, app/services/chat_prompt.py. Metric: docs/audit/06_RAG_EVALUATION_REPORT.md "
        "(100 synthetic cases). Hybrid has not been shown to beat vector-only.")


# ---------------------------------------------------------------- D04 Celery
def d04():
    queues = [("ingest", 250), ("crawl", 360), ("default", 470), ("maintenance", 640)]
    body = "".join([
        step(1, node(96, 330, 260, 130, "api", ("saves job row,", "then enqueues"), BLUE),
             node(96, 560, 300, 190, "beat", ("sweep every 120 s", "analytics hourly", "retention daily"), BLUE)),
        step(2, text(620, 220, "Redis queues", 22, ACCENT, 700, "middle"),
             *[node(500, y, 240, 80, q, (), ACCENT, 22) for q, y in queues],
             *[arrow([(356, 395), (430, 395), (430, y + 40), (500, y + 40)], "job") for _, y in queues[:2]],
             arrow([(396, 600), (460, 600), (460, 510), (500, 510)], "job"),
             arrow([(396, 690), (430, 690), (430, 680), (500, 680)], "job")),
        step(3, rect(900, 230, 560, 340, stroke=BLUE),
             text(930, 275, "worker · 2 slots · 2 GiB · 2 CPUs · 128 PIDs", 20, WHITE, 700),
             node(930, 300, 500, 90, "Claim job (compare-and-set)", ("attempt number fences stale work",), LINE, 20, 16),
             node(930, 410, 500, 130, "Fresh parser child process", (
                 "wall 60 s · CPU 30 s · 512 MiB · 32 MiB result", "containment, not a sandbox"), AMBER, 20, 16),
             arrow([(740, 290), (900, 290)], "job"), arrow([(740, 400), (900, 400)], "job"),
             arrow([(740, 510), (900, 510)], "job")),
        step(4, node(900, 620, 560, 120, "maintenance worker · 1 slot", (
                 "re-queues lost jobs · resets stuck jobs", "purges unpublished objects"), BLUE, 22, 17),
             arrow([(740, 680), (900, 680)], "job")),
        step(5, node(1560, 300, 264, 150, "PostgreSQL", ("job truth", "atomic publish")),
             node(1560, 540, 264, 120, "Object storage", ("originals",)),
             arrow([(1460, 350), (1560, 350)], "db"), arrow([(1460, 500), (1510, 500), (1510, 600), (1560, 600)], "obj")),
        step(6, text(900, 800, "Task limits: documents soft 120 s / hard 180 s · crawls up to 3240 s / 3300 s", 20, MUTED),
             text(900, 835, "A killed job waits for the sweep: about 17 minutes with default settings", 20, AMBER)),
        legend(["job", "db", "obj"]),
    ])
    svg("D04-celery-workers.svg", "Background processing", "Slow work leaves the request path",
        "code", body,
        "Source: app/workers/celery_app.py, app/rag/pipeline.py, parser_runner.py, docker-compose.yml; "
        "docs/INGESTION.md §7–8.")


# ---------------------------------------------------------------- D05 starvation
def d05():
    requests = "".join(node(96, 210 + i * 70, 200, 56, f"Chat {i + 1}", (), LINE, 19) for i in range(10))
    slots = "".join(
        rect(720 + (i % 5) * 120, 330 + (i // 5) * 120, 100, 100, fill="#3B1217", stroke=RED)
        + text(770 + (i % 5) * 120, 388 + (i // 5) * 120, f"held {i + 1}", 18, WHITE, 500, "middle")
        for i in range(10))
    body = "".join([
        step(1, requests),
        step(2, text(1010, 295, "Database pool: 5 + 5 overflow = 10", 22, WHITE, 700, "middle"), slots,
             arrow([(296, 440), (700, 440)], "sync", "① authentication keeps a connection", (500, 425))),
        step(3, arrow([(720, 620), (500, 620), (500, 560), (296, 560)], "bad",
                      "② asks for a second one: none left", (510, 655))),
        step(4, node(1420, 380, 400, 140, "Everyone waits 30 s", ("then HTTP 500",), RED),
             arrow([(1300, 450), (1420, 450)], "bad")),
        step(5, text(96, 960, "Measured before the fix: 10 concurrent requests → 10 × HTTP 500, P95 30,252 ms", 24, RED, 700)),
    ])
    svg("D05-pool-starvation.svg", "AUD-01 · Connection pool starvation",
        "Each request held one connection while waiting for another", "measured", body,
        "Source: docs/mvp-improvement/AUD-01_IMPLEMENTATION_REPORT.md §2–3, evidence/AUD-01/baseline.")


# ---------------------------------------------------------------- D06 admission
def d06():
    stages = [("Authorize", ("then release the", "DB connection")), ("Admission", ("3 chats per org", "wait ≤ 0.9 s")),
              ("Prepare", ("short transaction,", "bounded capacity")), ("Embed query", ("no DB connection",)),
              ("Stream", ("no DB connection",)), ("Finalize", ("save, release lease",))]
    parts = []
    for i, (title, detail) in enumerate(stages):
        x = 96 + i * 292
        block = [node(x, 330, 252, 160, title, detail, BLUE, 23, 17)]
        if i:
            block.append(arrow([(x - 40, 410), (x - 4, 410)], "sync"))
        parts.append(step(i + 1, *block))
    body = "".join([
        *parts,
        step(7, arrow([(514, 490), (514, 590)], "warn"),
             node(364, 600, 300, 90, "429 chat_busy", ("retry later",), AMBER, 22, 17),
             arrow([(806, 490), (806, 590)], "warn"),
             node(700, 600, 300, 90, "503 unavailable", ("setup or pool full",), AMBER, 22, 17)),
        step(8, rect(96, 760, 1728, 150, stroke=GREEN),
             text(130, 810, "Final local run, 100 concurrent requests", 24, GREEN, 700),
             text(130, 855, "67 served · 33 rejected with a controlled status · 0 failed · served P95 1,682 ms (gate 2,000 ms)", 23, WHITE),
             text(130, 890, "Offline fixture provider on one developer laptop: not a production capacity figure", 18, AMBER)),
        legend(["sync", "warn"]),
    ])
    svg("D06-admission-control.svg", "AUD-01 · Bounded admission and short database lifetimes",
        "Overload is refused early and cheaply instead of failing slowly", "measured", body,
        "Source: app/api/deps.py, app/services/chat_controls.py, conversations.py; "
        "evidence/MILESTONE-A-FINAL/final/suite-data/capacity-100.json.")


# ---------------------------------------------------------------- D07 provenance
def d07():
    body = "".join([
        step(1, text(96, 230, "Retrieved candidates", 22, ACCENT, 700),
             *[node(96, 260 + i * 130, 300, 100, f"Passage {n}", (d,), LINE, 22, 16)
               for i, (n, d) in enumerate([("A", "ranked 1st"), ("B", "ranked 2nd"), ("C", "ranked 3rd")])]),
        step(2, node(500, 330, 280, 220, "Re-authorize", ("reload from DB:", "org · bot ·", "published version"), BLUE, 23, 17),
             arrow([(396, 440), (500, 440)], "sync")),
        step(3, rect(900, 230, 420, 430, stroke=BLUE),
             text(1110, 272, "Rendered into the prompt", 22, WHITE, 700, "middle"),
             node(930, 295, 360, 100, "[1] Passage A", ("whole",), GREEN, 22, 16),
             node(930, 410, 360, 100, "[2] Passage B", ("partly fits",), GREEN, 22, 16),
             node(930, 525, 360, 100, "Passage C", ("budget full: not shown",), RED, 22, 16, dash="10 8"),
             arrow([(780, 440), (900, 440)], "sync")),
        step(4, node(1440, 330, 384, 220, "Model answer", ("“… [1] … [2] … [3]”",), LINE, 24, 22),
             arrow([(1320, 440), (1440, 440)], "ai")),
        step(5, node(900, 760, 924, 160, "Streaming citation filter", (
                 "[1] ✓ kept     [2] ✓ kept     [3] ✗ removed", "also when a marker is split across chunks"), ACCENT, 24, 20),
             arrow([(1632, 550), (1632, 760)], "sync")),
        step(6, text(96, 800, "Before: [3] was accepted", 24, RED, 700),
             text(96, 838, "although the model never saw Passage C.", 20, MUTED),
             text(96, 890, "Provenance, not correctness: a kept", 20, AMBER),
             text(96, 918, "citation may still not support the sentence.", 20, AMBER)),
    ])
    svg("D07-citation-provenance.svg", "AUD-02 · Exact citation provenance",
        "Only evidence actually placed in the prompt can be cited", "illustrative", body,
        "Source: app/rag/retrieval.py (render_evidence, authorize_chunks), app/services/chat_prompt.py. "
        "Passages are illustrative; the 12,000-byte context ceiling is real.")


# ---------------------------------------------------------------- D08 storage
def d08():
    stages = [("1 · Stage", ("record the new key", "“delete unless published”")),
              ("2 · Upload", ("new object every time", "…/g-{id}/original")),
              ("3 · Publish", ("fenced transaction:", "chunks + new key")),
              ("4 · Purge", ("old object queued,", "then removed"))]
    parts = []
    for i, (title, detail) in enumerate(stages):
        x = 96 + i * 448
        block = [node(x, 280, 384, 170, title, detail, BLUE, 25, 19)]
        if i:
            block.append(arrow([(x - 64, 365), (x - 4, 365)], "obj" if i == 1 else "db"))
        parts.append(step(i + 1, *block))
    body = "".join([
        *parts,
        step(5, node(544, 580, 832, 130, "Stale attempt A resumes after attempt B published", (
                 "it no longer owns the job → publication refused",), RED, 22, 18),
             arrow([(1184, 580), (1184, 450)], "bad"),
             node(544, 750, 832, 100, "Its object is reclaimed later", ("B’s original and chunks stay unchanged",), GREEN, 22, 18),
             arrow([(960, 710), (960, 750)], "ok")),
        step(6, text(96, 940, "Before: one fixed key per page, so A could overwrite B’s stored HTML.", 22, RED, 700),
             text(96, 975, "After: 20 of 20 ownership tests pass; three also against real object storage.", 20, GREEN)),
    ])
    svg("D08-immutable-storage.svg", "Immutable, fenced object publication",
        "An object write cannot join a database transaction, so ownership is decided at publish", "code", body,
        "Source: app/rag/originals.py, app/rag/storage.py; docs/mvp-improvement/A5_1_INGESTION_INTEGRITY_REPORT.md.")


# ---------------------------------------------------------------- D09 widget
def d09():
    body = "".join([
        step(1, node(96, 260, 300, 130, "Script tag", ("data-bot-key",), BLUE)),
        step(2, node(500, 260, 360, 130, "Page-wide registry", ("shared by every loader copy",), BLUE),
             arrow([(396, 325), (500, 325)], "sync")),
        step(3, node(964, 250, 400, 150, "Identity", ("API origin · page origin", "bot key · instance key"), ACCENT),
             arrow([(860, 325), (964, 325)], "sync")),
        step(4, node(1468, 190, 356, 110, "Exists", ("keep the same one",), GREEN),
             node(1468, 350, 356, 130, "New", ("1 iframe · 1 listener", "per-mount nonce"), BLUE),
             arrow([(1364, 300), (1416, 300), (1416, 245), (1468, 245)], "ok"),
             arrow([(1364, 345), (1416, 345), (1416, 415), (1468, 415)], "sync")),
        step(5, node(1468, 570, 356, 150, "Inside the frame", ("bootstrap or resume", "chat over SSE", "token stays in memory"), BLUE),
             arrow([(1646, 480), (1646, 570)], "sync")),
        step(6, node(964, 580, 400, 130, "destroy()", ("removes frame and listener", "ends its requests"), AMBER),
             arrow([(1468, 645), (1364, 645)], "sync")),
        step(7, node(500, 580, 360, 130, "Mount again", ("conversation resumes",), GREEN),
             arrow([(964, 645), (860, 645)], "sync")),
        step(8, text(96, 830, "forget: true asks the frame to delete the resume entry first; after 5 s without an answer", 20, MUTED),
             text(96, 860, "the widget is removed anyway and the entry may remain.", 20, AMBER),
             text(96, 920, "A cut-off answer is stored as interrupted and its reserved usage stays charged.", 20, MUTED),
             text(96, 960, "Loader: 5,248 gzip bytes of a 10,240 budget · tested in Chrome with localhost origins only", 22, WHITE, 700)),
    ])
    svg("D09-widget-lifecycle.svg", "Widget initialization lifecycle",
        "Safe to install twice, safe to remove, safe to bring back", "code", body,
        "Source: apps/widget/src/lifecycle.ts, loader.ts, panel.ts; docs/WIDGET_DEPLOYMENT.md; "
        "widget_assets/v1/manifest.json.")


# ---------------------------------------------------------------- D10 timeline
def d10():
    items = [("AUD-01", "Pool starvation", "admission control"), ("AUD-02", "Citation provenance", "rendered only"),
             ("AUD-03", "Provider transport", "HTTPS required"), ("AUD-04", "Proxy trust", "none by default"),
             ("AUD-05", "Parser limits", "contained child"), ("AUD-06", "Inbox gaps", "scoped cursors"),
             ("AUD-07", "Widget lifecycle", "dedupe + destroy")]
    parts = [f'<line x1="150" y1="470" x2="1770" y2="470" stroke="{LINE}" stroke-width="6"/>']
    for i, (code, title, fix) in enumerate(items):
        x = 180 + i * 260
        parts.append(step(i + 1,
                          f'<circle cx="{x}" cy="470" r="30" fill="{GREEN}"/>',
                          text(x, 480, "✓", 30, BG, 700, "middle"),
                          text(x, 400, code, 28, WHITE, 700, "middle"),
                          text(x, 560, title, 20, WHITE, 500, "middle"),
                          text(x, 592, fix, 18, MUTED, 400, "middle"),
                          text(x, 632, "local pass", 17, GREEN, 700, "middle")))
    body = "".join([
        *parts,
        step(8, node(96, 720, 830, 150, "Stabilization checkpoints", (
                 "A4.1 latency + migrations · A5.1 storage race · A6.1 latency",
                 "final: scheduler, CI configuration, backup and restore"), BLUE, 23, 19),
             node(990, 720, 834, 150, "Still open", (
                 "milestone closure waits on a migration policy decision",
                 "hosted CI never run · real AI quality untested"), AMBER, 23, 19)),
    ])
    svg("D10-remediation-timeline.svg", "Audit remediation, AUD-01 to AUD-07",
        "One focused fix at a time, each with its own report and regression tests", "measured", body,
        "Source: docs/mvp-improvement/MILESTONE_A_CLOSURE_MATRIX.md, 02_PROGRESS_TRACKER.md. "
        "Order is shown; spacing is not a time scale.")


# ---------------------------------------------------------------- D11 test growth
def d11():
    data = [("Audit", 582, 0), ("A1", 602, 2), ("A2", 635, 1), ("A3", 795, 0), ("A4", 1005, 2),
            ("A4.1", 1016, 0), ("A5", 1116, 0), ("A5.1", 1148, 0), ("A6", 1173, 1), ("A6.1", 1183, 0),
            ("A7", 1192, 0), ("Final", 1209, 0)]
    base, top, scale = 860, 240, 1300
    parts = [f'<line x1="96" y1="{base}" x2="1824" y2="{base}" stroke="{LINE}" stroke-width="3"/>']
    for i, (label, passed, failed) in enumerate(data):
        x = 126 + i * 142
        h = (base - top) * passed / scale
        block = [rect(x, base - h, 92, h, fill=GREEN if label == "Final" else BLUE, stroke="none", radius=8, width=0),
                 text(x + 46, base - h - 14, f"{passed:,}", 24, WHITE, 700, "middle"),
                 text(x + 46, base + 34, label, 19, MUTED, 500, "middle")]
        if failed:
            block.append(text(x + 46, base + 64, f"{failed} failed", 17, RED, 700, "middle"))
        parts.append(step(i + 1, *block))
    body = "".join([
        *parts,
        step(13, f'<line x1="680" y1="270" x2="680" y2="{base}" stroke="{MUTED}" stroke-width="2" stroke-dasharray="8 8"/>',
             text(670, 270, "Phase 7 (inbox + analytics) tests added here", 18, MUTED, 500, "end")),
        step(14, text(96, 970, "Backend pytest, passed per checkpoint. Failures shown were open findings or gate misses at that point.", 19, MUTED),
             text(96, 1000, "Final: 1,209 passed, 17 skipped (the runtime proxy tests, 17/17 run separately).", 19, WHITE)),
    ])
    svg("D11-test-growth.svg", "Backend test growth", "From the first audit to the final local run",
        "measured", body,
        "Sources: docs/audit/01_EXECUTIVE_SUMMARY.md and the report for each checkpoint in "
        "docs/mvp-improvement/. A count is not a coverage percentage.")


# ---------------------------------------------------------------- D12 performance
def d12():
    series = [("Unloaded", 140, [1625, 1701, 1735, 1649, 1606], [67, 64, 63, 65, 65], BLUE),
              ("While crawling", 1030, [1975, 1680, 1699, 1772, 1776], [54, 64, 63, 58, 60], ACCENT)]
    base, top, scale = 800, 260, 2200
    y_of = lambda v: base - (base - top) * v / scale  # noqa: E731
    parts = [f'<line x1="96" y1="{base}" x2="1824" y2="{base}" stroke="{LINE}" stroke-width="3"/>']
    for n, (name, x0, values, served, colour) in enumerate(series):
        block = [text(x0 + 375, 225, name, 24, WHITE, 700, "middle")]
        for i, (value, ok) in enumerate(zip(values, served, strict=True)):
            x = x0 + i * 150
            tight = value > 1900
            block += [rect(x, y_of(value), 100, base - y_of(value), fill=AMBER if tight else colour,
                           stroke="none", radius=8, width=0),
                      text(x + 50, y_of(value) + 34, f"{value:,}", 21, BG if tight else WHITE, 700, "middle"),
                      text(x + 50, base + 30, f"run {i + 1}", 17, MUTED, 400, "middle"),
                      text(x + 50, base + 56, f"{ok}/100 served", 16, MUTED, 400, "middle")]
        parts.append(step(n + 1, *block))
    gate = y_of(2000)
    body = "".join([
        *parts,
        step(3, f'<line x1="96" y1="{gate}" x2="1824" y2="{gate}" stroke="{AMBER}" stroke-width="3" stroke-dasharray="14 10"/>',
             text(960, gate - 12, "gate: 2,000 ms", 20, AMBER, 700, "middle")),
        step(4, text(96, 910, "10 of 10 declared runs passed. Tightest margin: 25 ms.", 28, GREEN, 700),
             text(96, 950, "P95 latency of served requests at 100 concurrent. The rest received a controlled rejection; none failed.", 20, WHITE),
             text(96, 984, "One laptop, offline fixture provider. A throttled host has exceeded the gate before.", 20, AMBER)),
    ])
    svg("D12-performance.svg", "Capacity acceptance results", "Final declared series, every run shown",
        "measured", body,
        "Source: evidence/MILESTONE-A-FINAL/perf/{unloaded-5,mixed-crawl-5}/summary.json; "
        "MILESTONE_A_VALIDATION_RESULTS.md.")


# ---------------------------------------------------------------- D13 backup
def d13():
    body = "".join([
        step(1, node(96, 280, 360, 200, "Source stack", ("writers and storage", "stopped (quiesced)"), BLUE)),
        step(2, node(560, 250, 360, 110, "Database dump", ("compressed SQL",), ACCENT),
             node(560, 390, 360, 110, "Document archive", ("+ SHA-256 checksums",), ACCENT),
             arrow([(456, 330), (560, 305)], "db"), arrow([(456, 430), (560, 445)], "obj")),
        step(3, node(1024, 280, 340, 200, "Restore", ("into empty volumes only", "all-or-nothing"), BLUE),
             arrow([(920, 305), (1024, 340)], "db"), arrow([(920, 445), (1024, 420)], "obj")),
        step(4, node(1468, 280, 356, 200, "verify-data", ("counts and hashes,", "policies, grants:", "identical"), GREEN),
             arrow([(1364, 380), (1468, 380)], "ok")),
        step(5, node(1024, 560, 800, 130, "The restored app answered the same", (
                 "sign-in · transcript · retrieval results · inbox",), GREEN, 24, 19),
             arrow([(1646, 480), (1646, 560)], "ok")),
        step(6, node(96, 560, 824, 130, "Defect found by the rehearsal, then fixed", (
                 "the restored database regained DELETE rights the source had revoked",), RED, 23, 19)),
        step(7, text(96, 790, "22 conversations, 32 messages, 6 chunks · backup 3 s · restore + verify 25 s", 23, WHITE, 700),
             text(96, 828, "Tiny synthetic data: no recovery-time claim.", 20, AMBER),
             text(96, 890, "Not covered: off-site copies, point-in-time recovery, alerting, production-sized data,", 20, AMBER),
             text(96, 920, "production Compose file.", 20, AMBER)),
        legend(["db", "obj", "ok"]),
    ])
    svg("D13-backup-restore.svg", "Backup and restore rehearsal", "A backup counts once it has been restored",
        "measured", body,
        "Source: deploy/backup.sh, deploy/restore.sh, docs/RECOVERY.md, "
        "evidence/MILESTONE-A-FINAL/final/ci/restore/summary.log.")


# ---------------------------------------------------------------- D14 roadmap
def d14():
    def column(x, title, colour, items):
        out = [rect(x, 220, 544, 700, stroke=colour), text(x + 272, 275, title, 28, colour, 700, "middle")]
        for i, item in enumerate(items):
            out.append(rect(x + 24, 310 + i * 84, 496, 68, fill=BG, stroke=LINE, radius=12))
            out.append(text(x + 48, 352 + i * 84, item, 20, WHITE, 500))
        return "".join(out)

    body = "".join([
        step(1, column(96, "Validated locally", GREEN, [
            "Core product workflows", "Tenant isolation tests", "AUD-01 to AUD-07 fixes",
            "Backup and restore rehearsal", "Capacity gate on one laptop", "CI scripts run on this machine"])),
        step(2, column(688, "Open now", AMBER, [
            "Migration recovery policy decision", "Commit and push the reviewed code", "First hosted CI run",
            "Real AI provider evaluation", "Semantic RAG quality (85% vs 90%)", "Production security and deployment"])),
        step(3, column(1280, "Future roadmap", MUTED, [
            "B · Real LLM and embeddings", "C · Reranking, query rewriting", "D–E · Knowledge, escalation",
            "F–G · Analytics, knowledge gaps", "H–I · UX, production readiness", "J · Expanded evaluation"])),
    ])
    svg("D14-roadmap.svg", "Where the project stands", "Future work is a plan, not a feature", "plan", body,
        "Source: MILESTONE_A_FINAL_REPORT.md, MILESTONE_A_RISK_REGISTER.md, docs/MVP_IMPROVEMENT_PLAN.md. "
        "Re-check on the day of recording.")


# ---------------------------------------------------------------- overlays and cards
def overlays():
    ASSETS.mkdir(exist_ok=True)

    def pill(name, label, colour, w):
        (ASSETS / name).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="56" viewBox="0 0 {w} 56">'
            f'{rect(2, 2, w - 4, 52, fill=BG, stroke=colour, radius=26)}'
            f'<circle cx="32" cy="28" r="7" fill="{colour}"/>{text(54, 35, label, 20, WHITE, 600)}</svg>\n',
            encoding="utf-8", newline="\n")

    pill("label-demo.svg", "Deterministic local demonstration · canned demo reply · hash embeddings", AMBER, 760)
    pill("label-local.svg", "Local validation · not production · not independently certified", AMBER, 650)

    def card(name, extra):
        (ASSETS / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">'
            f'<defs><radialGradient id="glow" cx="50%" cy="42%" r="55%"><stop offset="0" stop-color="{BLUE}" '
            f'stop-opacity="0.22"/><stop offset="1" stop-color="{BG}" stop-opacity="0"/></radialGradient></defs>'
            f'<rect width="1920" height="1080" fill="{BG}"/><rect width="1920" height="1080" fill="url(#glow)"/>'
            f'<g id="title">{text(960, 440, "Multi-Tenant AI Customer Support", 76, WHITE, 700, "middle")}'
            f'{text(960, 535, "Platform with RAG", 76, WHITE, 700, "middle")}</g>'
            f'<rect id="rule" x="760" y="590" width="400" height="6" rx="3" fill="{BLUE}"/>{extra}</svg>\n',
            encoding="utf-8", newline="\n")

    card("title-card.svg", text(960, 672, "A technical case study", 32, MUTED, 500, "middle"))
    card("end-card.svg",
         text(960, 672, "Software Engineering  ·  Full-Stack Development  ·  AI Engineering", 30, MUTED, 500, "middle")
         + text(960, 780, "Portfolio: venuja.online", 38, ACCENT, 700, "middle"))


if __name__ == "__main__":
    for build in (d01, d02, d03, d04, d05, d06, d07, d08, d09, d10, d11, d12, d13, d14, overlays):
        build()
    print("built", len(list(HERE.glob("D*.svg"))), "diagrams and", len(list(ASSETS.glob("*.svg"))), "assets")
