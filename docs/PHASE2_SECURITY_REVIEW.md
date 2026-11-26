# Phase 2 — Identity, Tenancy & RBAC: Security Review and Migration Guide

| Field | Value |
|---|---|
| Date | 2026-11-22 |
| Scope | Registration/login/sessions, email verification, password recovery, organizations and switching, invitations, RBAC, membership management, audit logging, RLS |
| Roadmap name | "Phase 1 — Identity, tenancy & RBAC" in [ROADMAP](ROADMAP.md) (the project brief calls it Phase 2) |
| Related | [SECURITY](SECURITY.md) · [DATABASE](DATABASE.md) · [ARCHITECTURE](ARCHITECTURE.md) · ADR-005, ADR-033 in [DECISIONS](DECISIONS.md) |

**Gate status:** the tenant-isolation tests pass (41 tests across the RLS suite, the HTTP isolation suite, the route-permission matrix and the concurrency tests), as do all other tests. Phase 3 may start once the open items in §5 are triaged.

---

## 1. What was built

| Area | Implementation |
|---|---|
| Sessions | Opaque 256-bit token in a `__Host-session` cookie (`HttpOnly; Secure; SameSite=Lax; Path=/`, no `Domain`). Only the SHA-256 hash is stored. 14-day idle / 30-day absolute expiry. Rotated on login and password change; a presented cookie is revoked at login (fixation defence). |
| Validation | Every request is checked against Postgres (no cache): session not revoked/expired/idle **and** user `active`. Logout, disable, reset and membership removal apply on the next request. |
| Passwords | Argon2id (19 MiB, t=2, p=1), 10–128 chars, no composition rules, blocklist + "contains email" check, off-loop hashing, dummy verification for unknown users, auto-rehash. |
| Email verify / reset | 256-bit single-use tokens, hashed at rest, atomic `UPDATE … RETURNING` consumption, purpose-bound, 48 h / 30 min TTL, a new token voids older ones. Reset revokes **all** sessions and clears lockout. |
| Anti-enumeration | Same status/body for login failures, forgot-password, and signup with an existing email (decoy payload, notification email to the real owner). Argon2 work is done in every branch. |
| Rate limiting | Redis fixed windows, keys hashed: login per IP (10/min, 100/h) and per email (5/min, 20/h), 5-failure 15-minute lock keyed by email hash (works for unknown emails), signup, forgot/resend (3/h per email), invitation lookup. **Fails closed** (503) if Redis is down. |
| CSRF | `X-Requested-With: platform` required on all unsafe `/api/` requests plus an `Origin` allowlist; CORS allows only configured origins with credentials. |
| Tenancy | Org id comes from the URL path and is **verified on every request** against the caller's own membership. Non-member → 404 (same body as a non-existent org). Bodies reject unknown fields (`extra="forbid"`), so `org_id`, `role`, `status` can't be mass-assigned. |
| RBAC | Roles `owner > admin > agent > viewer`; one declared permission per org route (asserted by a test); pure-function policy for role change/removal/leave/transfer. |
| Invitations | 7-day expiring, single-use, email-bound tokens; atomic accept; resend rotates the token; owner role can't be invited (CHECK + schema + policy). |
| Audit | `audit_logs`: append-only for the runtime role. Rows for org create/update, invite/resend/revoke/accept, role change, remove/leave, ownership transfer (actor, target, request id, /24 IP prefix, no secrets). |
| Database | Migration `0002`: FORCE RLS on all tenant tables, self-join-only membership INSERT, no org DELETE policy, last-owner and immutable-identity trigger, CHECK constraints, `app.resolve_invitation()` definer function. Runtime role has no superuser/BYPASSRLS (asserted). |
| Frontend | Sign up/in/out, verify, forgot/reset, invitation acceptance, org switcher (navigation only), members + invitations, settings (rename, transfer ownership, activity), account (profile, password, devices). Auth is a client-side cache of `GET /me`; no secrets in browser storage. |

## 2. Threat checklist against the brief

| Requirement | Evidence |
|---|---|
| Enforce tenant ownership on every protected request | `get_tenant_context` + `require()`; auto-discovered sweep asserts **every** `{org_id}` route returns 404 to a non-member and 401 without a session (`test_tenant_isolation.py`); route-permission matrix test fails any route lacking a declared permission. |
| Never trust client org ids | Org id is only a claim in the path; GUC is set from the DB-returned membership. Tests send `X-Org-Id` headers, query and body org ids — all ignored/rejected. |
| Verify membership + permissions server-side | Membership read under RLS on each request; roles re-read each time (a demoted admin gets 403 on the next call). |
| Row-Level Security | `FORCE` RLS on `organizations`, `memberships`, `invitations`, `audit_logs`; `app` role without GUCs sees 0 rows; cross-org INSERT/UPDATE/DELETE blocked; CI step `python -m app.cli check-rls` fails any `org_id` table without RLS+policy. |
| No privileged DB credentials exposed | API/worker use `platform_app` (`NOSUPERUSER NOBYPASSRLS`, verified through the API's own pool). Migration owner URL is only used by Alembic. No DB URL reaches the browser. |
| Cookie/session protection | See §1; attributes asserted in tests; HttpOnly keeps tokens from scripts; `__Host-` blocks subdomain overwrite. |
| Rate-limit auth endpoints | Tests: 6th failed login → 429 + `Retry-After`; unknown emails throttled identically; forgot/resend 3/h; lookup limiter. |
| Prevent role escalation | Admin can't change/remove owners, nobody can self-change, "owner" isn't assignable or invitable, only an owner can transfer (with password re-entry, target must be an admin); DB trigger blocks last-owner removal and identity edits. |
| Prevent cross-org access | IDOR tests: another org's membership/invitation ids under my org → 404; switching orgs and leaving orgs never leaks or keeps access. |

### Mutation checks (do the tests have teeth?)
The tenant tests were mutation-tested by hand: (1) setting the org context from the URL before verifying membership **fails 6 isolation tests**; (2) removing the permission check fails the RBAC tests; (3) removing the app-level user filter while keeping RLS **still passes**, demonstrating that Postgres blocks the leak by itself (defence in depth).

## 3. Test inventory

| Suite | Count |
|---|---|
| Backend unit (policy matrix, token/password primitives, config guards, existing) | 83 |
| Backend integration: RLS + constraints + RLS lint | 24 |
| Backend integration: auth/sessions/verification/reset/CSRF/CORS | 50 |
| Backend integration: orgs, members, RBAC, audit | 22 |
| Backend integration: invitations | 21 |
| Backend integration: tenant isolation sweep, switching, pool context | 13 |
| Backend integration: route-permission matrix; concurrency (12 racers); log hygiene | 2 + 2 + 1 |
| Frontend (Vitest + Testing Library): API client, redirects, validation, auth context, guards, forms, switcher, members, invitation, verify | 122 |

Total: backend 220, frontend 122 (+7 existing widget tests). Lint, strict mypy, Ruff, ESLint, `tsc`, Prettier and the production Next build all pass; the dev stack was also exercised in a real browser (signup → client validation → verify via Mailpit link, replay rejected → members → invitation).

## 4. Deviations from the docs (all recorded in ADR-033 / ADR-005)

- Role `editor` renamed **`agent`** (same permissions), per the brief.
- No Redis caching of sessions or memberships (docs ARCH §14 suggested 60 s): chosen so revocation is immediate.
- Invitation **list** requires `member:invite` (docs said `member:read`): least privilege for invited emails.
- Emails go out in-process after the response, not via Celery, so tokens never sit on the broker.
- Auth events (failed logins, resets) are structured security logs, not tenant audit rows (no org context). Tenant actions are in `audit_logs`.
- Owner-role read policies stand in for the `platform_system` BYPASSRLS role from DATABASE §4.1 (not created yet).

## 5. Residual risks and open items (honest list)

| # | Item | Severity | Notes / action |
|---|---|---|---|
| 1 | **Client IP trust.** The production image runs uvicorn with `--forwarded-allow-ips "*"`. If the API is reachable directly, a client can forge `X-Forwarded-For` and evade IP rate limits and skew the audit IP prefix. | Medium | Pre-existing Dockerfile setting. Before production, restrict it to the load balancer's addresses (or terminate proxying at a trusted hop). Per-email limits and lockout are unaffected. |
| 2 | **Redis outage = auth unavailable** (fail-closed). | Low (by design) | Revisit with an in-process fallback limiter if availability matters more. |
| 3 | No breach-corpus (HIBP) lookup; offline blocklist only. | Low | SECURITY §3 target; add k-anonymity lookup. |
| 4 | Timing equalisation (dummy Argon2) is implemented but AC1.4's "within 50 ms p95" is **not** statistically measured. | Low | Add a timing probe in staging. |
| 5 | Playwright E2E (AC1.10) not written; the flow was walked manually. | Medium (process) | Needs the Playwright package (ROADMAP "later"). |
| 6 | No nonce-based CSP yet (baseline headers added: `frame-ancestors 'none'`, nosniff, referrer, permissions). | Low–Med | Track with Phase 9 hardening. |
| 7 | Audit pagination cursor is unsigned (API_SPEC §1.3 wants HMAC). | Low | Data is RLS-scoped, so tampering can't cross tenants. |
| 8 | Org deletion/restore, email change, MFA, SSO, per-session "active sessions" IP/UA display polish, OpenAPI client generation not in scope. | — | Next phases / post-MVP. |
| 9 | In production the `__Host-` cookie set by `api.` is not visible to `app.` (different hosts), so route protection is client-side via `/me`. | Info | Matches the "ADR-021: no second auth system in Next.js" decision; the API remains the only authority. |
| 10 | Dev `LOG` email backend prints token links to logs. | Info | `EMAIL_BACKEND=log` is refused in production by config validation. |

## 6. Migration instructions

**Prerequisites:** Phase 0 database bootstrap is applied (`platform_owner` migrates; `platform_app` is `NOSUPERUSER NOBYPASSRLS`; extensions `citext`, `pgcrypto`). Migration `0002` only adds tables, so existing data is unaffected.

### Local (Docker)

```powershell
docker compose up -d --build --wait
```

`--build` matters: the `migrate` job bakes migrations into the image, so a stale image won't see `0002`. New services/vars come with it: Mailpit (UI http://localhost:8025) and `EMAIL_BACKEND`, `SMTP_*`, `WEB_BASE_URL` (add them to your `.env` from `.env.example` if you run the API natively).

Verify:

```powershell
docker compose exec api alembic current
```

Expected `0002 (head)`; then:

```powershell
docker compose exec api python -m app.cli check-rls
```

Expected `{"status": "ok", "unprotected_tables": []}`.

### Staging / production

1. Deploy the new image; run the **migration job first** (`alembic upgrade head`, as the schema owner via `MIGRATION_DATABASE_URL`), then roll the API/web containers.
2. Set: `EMAIL_BACKEND=smtp` plus `SMTP_*` for a real relay, `WEB_BASE_URL=https://app.<domain>` (HTTPS enforced), `CORS_ALLOWED_ORIGINS=https://app.<domain>`. Startup refuses `log` email, non-HTTPS URLs and placeholder credentials in production.
3. Restrict `--forwarded-allow-ips` to the load balancer (§5 item 1).
4. Confirm the runtime role: `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'platform_app'` → both `false`.
5. Smoke: `/readyz` (migration head = `0002`), sign up, verify email, invite, accept, remove, confirm the removed user gets 404 on the org.
6. CI runs `alembic upgrade → downgrade base → upgrade`, `check-rls`, and the integration suite (including the tenancy suite) against ephemeral Postgres/Redis.

### Rollback

```powershell
docker compose exec api alembic downgrade 0001
```

**Destructive:** this drops `users`, `sessions`, `email_tokens`, `organizations`, `memberships`, `invitations` and `audit_logs`. Do not run it against a database holding real accounts without a backup. Prefer a forward fix.

### Running the checks yourself

```powershell
docker compose exec api pytest -q
```

```powershell
docker compose exec api sh -c "ruff check . && ruff format --check . && mypy"
```

```powershell
corepack pnpm -r --if-present test
```

Integration tests create (and drop) their own throwaway database from `MIGRATION_DATABASE_URL`, so development data is never touched; they use Redis DB 15, which they flush.

## Status update: AUD-04 (additive; the sections above describe the earlier build)

Residual risk 1 in section 5 and migration step 3 in section 6 are superseded for the application image. The runtime image no longer passes `--forwarded-allow-ips "*"`; no peer is trusted unless listed in `FORWARDED_ALLOW_IPS`, which is validated at startup (DEVELOPMENT.md section 10). Verified locally against the runtime image: [AUD-04 report](mvp-improvement/AUD-04_IMPLEMENTATION_REPORT.md). Still open: the operator must configure the real proxy address and block direct access to the API, and neither has been verified on a live deployment.
