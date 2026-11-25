# Prioritized remediation plan

These are proposed changes for review after the audit. No application code was changed. The order follows risk and dependency; no delivery-date estimate is invented.

## P0 — release gates

1. **AUD-01 — API/database owner:** remove nested pool acquisition while an authenticated request transaction is held; release auth resources before streaming; apply admission controls before scarce-resource checkout. Preserve tenant-scoped session/RLS semantics and cancellation cleanup. Add bounded waits and controlled overload responses. Exit gate: repeat 1/10/50/100 local stages; zero unexpected 500s; documented 429/503 responses permitted; a second tenant remains responsive; quotas/leases reconcile after cancellation.
2. **AUD-02 — RAG/chat owner:** make prompt assembly return the exact rendered source set; compute escaped-content budgets consistently and validate citations against that set. Exit gate: current failing omission regression passes, including escaping/metadata/history edge cases, and no marker resolves to absent evidence.
3. **AUD-03/AUD-04 — platform/security owner:** reject HTTP provider endpoints in production, validate redirect behavior, restrict trusted proxies and enforce the direct-ingress boundary. Exit gate: failing HTTPS settings regression passes and an untrusted peer cannot choose its limiter IP using forwarded headers. Validate real deployment topology before release.
4. **Live AI verification — AI/QA owner:** configure an approved server-side model and embedding provider, reindex the supplied fictional corpus and run the 100-case evaluation. Review labels and grade real answers/claims/citations/refusals; retain model/version/settings and redacted results. Require >=90% correctness, >=95% faithfulness, >=90% Recall@5, >=95% citation accuracy, >=95% appropriate refusal and zero tenant leakage. If targets are revised, justify changes before evaluating rather than fitting them to results. No credential belongs in browser code or report logs.

## P1 — hardening and completeness

5. **AUD-05 — ingestion/platform owner:** isolate document parsing with hard wall-clock/resource budgets and cancellation/cleanup. Preserve existing magic-byte, zip and extraction limits. Test a bounded hostile/malformed fixture in a disposable worker and demonstrate queue recovery.
6. **AUD-06 — dashboard owner:** replace the unconditional empty inbox with the Phase 1–6 data actually promised, or clearly label its availability. Preserve stored conversations. Do not expand into Phase 7 analytics without a separate request. Test widget conversation visibility and refresh only if that UI is brought into current scope.
7. **AUD-07 — widget owner:** define repeated initialization semantics, make the default idempotent and add a teardown path; preserve intentionally separate bot instances. Test duplicate same-key scripts, navigation/remount and listener cleanup in plain HTML and Next.js.
8. **Platform/privacy/QA owners:** document physical retention behavior and implement it only in an authorized follow-up; verify public DNS lifecycle, bucket/IAM restrictions, restore drill, health/alerting, keyboard/assistive technology and browser network/console fault paths.

## Reverification gate

Run the current original suites and the deliberately failing audit regressions after fixes. Rerun targeted checks when changes affect their assumptions, then repeat the staged workload and real-provider dataset with explicit costs/limits. Retain before/after artifacts, distinguish fixture from real-provider results, verify source citations manually, and obtain a new readiness decision. A numeric score alone cannot waive unresolved HIGH risk or unverified critical end-to-end AI behavior.
