# Analytics metric definitions

| Field | Value |
|---|---|
| Status | Phase 7 |
| Date | 2026-11-25 |
| Related | [PRD](PRD.md) · [API_SPEC](API_SPEC.md) · [CHAT_ENGINE](CHAT_ENGINE.md) |

These definitions are implemented in `services/api/app/services/analytics_metrics.py` and the live queries in `services/api/app/services/analytics.py`. The dashboard never displays mock or placeholder numbers.

All queries, rollups, exports and deletes are organization-scoped (`org_id` on every row, FORCE RLS, membership check on every route).

## Population

| Set | Included | Excluded |
|---|---|---|
| Product metrics | `channel=widget` (and later messaging channels) | `channel=playground` |
| Usage / estimated cost | All channels, including playground | Unsettled reservations |

Playground traffic is listed in the inbox so staff can review test chats. It does not inflate resolution, satisfaction, grounded rate or unanswered rate.

## Conversation outcomes

Status is a **first-class field** on `conversations`, changed only by an explicit staff action or a handoff request. Completing an assistant reply does **not** change status.

| Status | Meaning |
|---|---|
| `open` | In progress. Default for every new conversation. |
| `resolved` | A teammate marked the issue resolved. |
| `unresolved` | A teammate marked that the issue was not resolved. |
| `handed_off` | A human-handoff request is the current outcome. Completing a handoff does not auto-resolve. |

**Resolution rate** = `resolved / (resolved + unresolved + handed_off)`

Open conversations are excluded. If nothing has been closed, the rate is undefined (`null`), not 0% or 100%. An AI answer is not a resolution.

## Customer satisfaction

Conversation-level CSAT is a persisted event (`satisfaction_submitted`) with a score from 1–5. It is distinct from per-answer thumbs on a message.

**Satisfaction rate** = count of CSAT scores ≥ 4 / count of CSAT submissions.

Unrated conversations are excluded. Message thumbs (`feedback_up` / `feedback_down`) are reported separately as **thumbs-up ratio** = up / (up + down).

## Grounding and unanswered questions

**Grounded rate** = finished assistant replies that stored at least one citation snapshot / finished assistant replies (`complete` or `fallback`).

**Unanswered rate** = unanswered-question events / customer (user) messages.

These are not inverses of each other. An unanswered event is written when:

- the model returns the insufficient-evidence fallback (`reason=insufficient_evidence`), or
- staff mark the latest question unanswered (`reason=marked_unanswered` or `ambiguous_query`).

Knowledge-gap reports group those events by chatbot and a normalized token `cluster_key`, then merge keys with Jaccard similarity ≥ 0.6. Semantic paraphrase clustering needs a production embedding model and is not claimed here.

## Usage and cost

Token and cost figures come from settled `chat_usage` rows and message token columns. **Estimated AI cost** is labelled as an estimate. Deleting a conversation removes the transcript; usage rows are kept so cost history survives.

## Charts

- Daily and monthly conversation charts count production conversations by UTC `created_at`.
- Token charts count settled usage, including playground.

## Retention and deletion

Default retention is **365 days** (configurable per organization from 1–730 via `organizations.settings.conversation_retention_days`). The daily job deletes conversations whose `last_message_at` is older than that window, plus aged unanswered rows and events, after snapshotting `analytics_daily`. Manual delete (`conversation:delete`) snapshots daily totals, then removes the transcript. Live inbox and summary counts follow remaining transcripts; `analytics_daily` keeps volume and outcome totals for purged days (no message content).

## CSV export

`POST /orgs/{org_id}/conversations/exports` requires `conversation:export` (admin and owner). The file is stored under `orgs/{org_id}/exports/` and downloaded only through the authorized API. Cross-tenant IDs return 404. Viewers and agents receive 403.
