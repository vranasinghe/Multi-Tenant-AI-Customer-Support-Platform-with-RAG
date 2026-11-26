# Screen recording checklist

## 0. State of the footage

Draft clips **R01–R15 exist** in `output/video/portfolio/clips/` (recorded 26 November 2026 by
[record.cjs](recording-scripts/record.cjs); 1920×1080, 30 fps container, no audio, gitignored).
Stills are in `output/video/portfolio/stills/`. They are intermediates: watch each one through
before using it. Frame rate of the actual capture follows screen changes, so check smoothness.

**Not recorded:** the terminal, code and CI shots T-1…T-5 and C-1…C-4 (manual, section 3), your
voice, any music, and the final videos.

How to re-record: [recording-scripts/README.md](recording-scripts/README.md). The earlier clips in
`output/video/` are obsolete (fact check X3).

## 1. Rules for every shot

- Disposable stack only (`demo` LLM, `hash` embeddings, no keys). Never the developer stack, never
  real customer data. Do not restart the developer worker or scheduler.
- Synthetic people: Maya Perera (Northwind Outdoor), Ravi Silva (Bluepeak Fitness), `@example.com`
  addresses. Files: [assets/demo-data/](assets/demo-data).
- Never on screen: `.env` or `ci.env`, `demo-account.txt`, DevTools network or storage panels,
  cookies, tokens, resume tokens, public keys, DNS proofs, organization ids, your own e-mail,
  bookmarks, notifications.
- Window 1536×864 at 125% device scale (= 1920×1080). Full screen, no address bar.
- Crops are in the final 1920×1080 frame as `x,y,w,h`. “Full” = whole frame in a rounded window.

## 2. Application clips

All start from the state the previous clip leaves. “Evidence” is what must be visible for the shot
to be usable.

| ID | Route | Start state | Data | Actions | Expected result (evidence) | Draft s / use s | Crop → highlight | Narration |
|---|---|---|---|---|---|---|---|---|
| R01 | `/login` | Signed out; Maya registered and verified off camera | Maya | Type e-mail and password, **Sign in** | Organization overview | 12 / 4 | Full → form, then sidebar | B03 |
| R02 | `/orgs/{org}` | Signed in, no bots | — | Hold, scroll | Overview cards at zero | 6 / 3 | `320,0,1600,720` (hide checklist, X12) → cards | B01, B03, A1 |
| R03 | `…/chatbots/new` | No bots | “Northwind Assistant”, short description, colour `#0F766E` | Five steps, **Create chatbot** | “Chatbot created” | 29 / 9 (speed ×2.5) | Full → step list | B03, A2 |
| R04 | `…/knowledge` | Bot exists, no documents | two Northwind TXT files | Choose both; wait; open **Passages** | Queued → Processing → Ready; passage dialog | 15 / 9 | `320,600,1600,480` → status column | B03, A2 |
| R05 | `…/knowledge` → Test retrieval | Both Ready | “How many days are returns allowed after delivery?” | **Search** (Hybrid) | Returns passage first, “model hash-v1” | 17 / 6 | `320,300,1500,600` → rank line | B03, B05 |
| R06 | `…/knowledge` → Websites | — | `http://169.254.169.254/latest/meta-data/` | Tick permission, **Add website** | “Only public websites can be crawled” | 17 / 6 | `320,300,960,700` → red message | B03 |
| R07 | `…/chatbots/{bot}` → Test chat | Documents Ready | “Are returns allowed within thirty days of delivery?” then “Explain astrophysics quasars galaxies?” | Send; **Helpful**; **New conversation**; send | Demo reply + `[1]` source; then “Insufficient evidence” | 31 / 14 | `320,150,1180,650` → source line, then label | B03, A3 |
| R08 | same → Install | Bot Draft | origins `http://localhost:3511`, dashboard | Status **Active**; Install; add + verify origins; copy; reload preview, open it | “Verified until…”, preview widget opens | 32 / 6 | `320,0,1300,900` → verified line. **Existing take: frames 211–230 (7.0–7.7 s) show the public key and script unblurred; never use that range.** Recorder fixed since, not re-recorded | B03 |
| R09 | `http://localhost:3511` | Bot Active, origin verified | same returns question | Open launcher, send, **Helpful**, reload, reopen | Demo reply + source; history after reload | 26 / 7 + 10 | Full, then `1360,380,560,700` → source | B03, B08, A1, A3 |
| R10 | `/harness` (test page) | — | — | Add same tag; mount second; destroy default; mount | Counter 1 → 1 → 2 → 1 → 2 | 21 / 14 | `0,0,1300,800` → counter | B08 |
| R11 | shop at 390 px | — | “Do tents carry a warranty?” | Open, send | Widget fits width; source shown | 15 / 10 | Centred phone frame (side bars are `#080C14`) | B08 |
| R12 | `…/conversations` → transcript | Widget chats exist | — | Open widget conversation; **Mark resolved**; scroll | Transcript with sources; status Resolved | 17 / 7 | `320,0,1600,900` → status, then sources. Skip list rows titled “Empty conversation” (opened-but-unused widgets) | B03, A3 |
| R13 | `…/analytics` | After R12 | — | Hold on cards | Conversations, resolution, satisfaction, grounded rate | 11 / 4 | `320,150,1600,300` → first row **only** (X8, X9, X10) | B03 |
| R14 | Bluepeak session | Bluepeak has own bot and document | Ravi | Own Knowledge page; then open Northwind's conversations URL | “Organization not found” | 11 / 8 | `320,60,1000,420` → message | B06 |
| R15 | `/orgs/{org}` | After the chats | — | Hold, scroll | 1 active bot, 4 conversations | 7 / 4 | `320,0,1600,320` (X12) | B01, B12, A1 |

R14 also writes `tenant-isolation-statuses.txt` (`404` for the other organization, `200` for its
own). Typeset it as a card; it contains no identifiers.

Website crawling: the script shows the **refusal** only, because a local synthetic site cannot be
crawled (that is the protection working). To film a successful crawl, set `PUBLIC_SITE_URL` to a
public site **you own**; it sends real requests to that site. Without it, do not narrate or imply a
successful crawl.

## 3. Manual captures (OBS)

OBS: 1920×1080 canvas and output, 30 fps, CQP 16–18, MKV (remux to MP4), display capture of one
window only. Terminal: new profile, 20 pt monospace, dark, prompt without your user name or path
(`function prompt { '> ' }`). Close everything else.

These show **stored evidence files**. Show the file name on screen, and never present them as a
live run. To show a live run instead, run the suite on a disposable stack and record that.

| ID | What | Command (PowerShell, repository root) | Highlight | s | Narration |
|---|---|---|---|---|---|
| T-1 | Backend result | `Get-Content docs/mvp-improvement/evidence/MILESTONE-A-FINAL/final/backend-full.log -Tail 3` | `1209 passed, 17 skipped` | 5 | B09 |
| T-2 | Frontend and bundle | `Select-String 'Tests ','loader.js:' docs/mvp-improvement/evidence/MILESTONE-A-FINAL/final/web-2.log \| ForEach-Object Line` | `19 passed`, `243 passed`, `5248 B` | 5 | B08, B09 |
| T-3 | Browser journeys | `Select-String 'passed' docs/mvp-improvement/evidence/MILESTONE-A-FINAL/final/browser.log \| ForEach-Object Line` | `17 passed` | 4 | B09 |
| T-4 | Mutation checks | `Get-Content docs/mvp-improvement/evidence/MILESTONE-A-FINAL/verification/mutants-all.json -TotalCount 14` | `"killed": true` | 4 | B09 |
| T-5 | CI configuration (a file, not a run) | open [ci.yml](../../.github/workflows/ci.yml) in the editor, jobs section | job names; overlay amber “Configured · never run on GitHub” | 5 | B09 |
| T-6 | Restore evidence | `Get-Content docs/mvp-improvement/evidence/MILESTONE-A-FINAL/final/ci/restore/summary.log` | rows, `backup_seconds=3` | 4 | B09 |
| C-1 | Admission | `services/api/app/services/chat_controls.py` lines 116–152 | `deadline`, `raise` | 6 | B07 |
| C-2 | Rendered evidence | `services/api/app/rag/retrieval.py` lines 271–282 | docstring | 5 | B07 |
| C-3 | Parser limits | `services/api/app/rag/parser_process.py` lines 50–75 | `RLIMIT_*` | 5 | B07 |
| C-4 | Adopt original | `services/api/app/rag/originals.py` lines 59–74 | `attempts = 0` | 5 | B07 |

Code shots: 22 pt or larger, at most 14 lines on screen, line numbers on, no minimap, no
file tree showing `.env`.

Before using a log: read the whole visible frame for local paths (`C:\Users\…`) and blur them.
The raw JSON command records in `final/*.json` contain such paths: **do not film them**.

## 4. Pre-flight for a re-record

- [ ] `docker ps` shows the disposable project; the developer containers are untouched
- [ ] Script prints `preflight ok: demo LLM, hash embeddings, no provider key`
- [ ] `manifest.json` lists every clip as `recorded`
- [ ] Watched every clip; no `*-FAILED.png` in stills
- [ ] Disposable stack removed afterwards (`docker compose down -v`)
