# Reproducible execution log

Commands below were actually executed from the repository root during this audit. Exit codes and wall times come from captured subprocess metadata, not estimated timings. Logs/JUnit are in `evidence/`. Environment was local Docker with loopback ports; no production database or paid model was used. The audit fixtures create/drop disposable databases, use isolated Redis test state and synthetic credentials. Browser tests create disposable local application accounts via Mailpit.

| ID | Actual command | Exit | Wall seconds | Evidence |
|---|---|---|---|---|
| audit_runtime | `docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/implementation_audit api pytest tests/integration/api/audit tests/unit/audit -q --tb=short --junitxml=/tmp/audit-added.xml` | 1 | 100.372 | `evidence/audit_runtime.log` |
| audit_static | `docker compose exec -T api ruff check .; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; docker compose exec -T api ruff format --check .; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; docker compose exec -T api mypy` | 0 | 6.85 | `evidence/audit_static.log` |
| audit_workflow | `docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/implementation_audit api pytest tests/integration/api/audit/test_implementation_audit.py::test_business_workflow_and_100_case_evaluation -q --tb=short --junitxml=/tmp/audit-workflow.xml` | 0 | 15.717 | `evidence/audit_workflow.log` |
| backend_build | `docker build --target runtime -t acs-audit-runtime services/api` | 0 | 4.164 | `evidence/backend_build.log` |
| backend_static | `docker compose exec -T api ruff check app migrations; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; docker compose exec -T api mypy app migrations` | 0 | 3.389 | `evidence/backend_static.log` |
| baseline_backend | `docker compose exec -T -e LIVE_INGESTION=1 api pytest -q --junitxml=/tmp/audit-baseline.xml` | 0 | 97.248 | `evidence/baseline_backend.log` |
| browser | `corepack pnpm --filter @acs/web exec playwright test --reporter=json` | 0 | 13.676 | `evidence/browser.log` |
| dependency_node | `corepack pnpm audit --json` | 0 | 3.065 | `evidence/dependency_node.log` |
| dependency_python | `docker compose exec -T api uv export --no-dev --format requirements-txt --no-hashes --no-emit-project \| Set-Content docs/audit/evidence/python_requirements.txt; uvx --from pip-audit pip-audit -r docs/audit/evidence/python_requirements.txt --no-deps --disable-pip --format=json` | 0 | 22.041 | `evidence/dependency_python.log` |
| environment | `docker compose ps; Get-Content docs/audit/tools/environment.py \| docker compose exec -T api python -; node --version; pnpm --version; uv --version` | 0 | 1.743 | `evidence/environment.log` |
| frontend_build | `corepack pnpm -r --if-present build` | 0 | 11.461 | `evidence/frontend_build.log` |
| frontend_lint | `corepack pnpm -r --if-present lint` | 0 | 11.271 | `evidence/frontend_lint.log` |
| frontend_tests | `corepack pnpm -r --if-present test` | 0 | 16.931 | `evidence/frontend_tests.log` |
| frontend_types | `corepack pnpm -r --if-present typecheck` | 0 | 5.554 | `evidence/frontend_types.log` |
| health_rls | `node scripts/smoke.mjs; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; docker compose exec -T api python -m app.cli check-rls` | 0 | 2.919 | `evidence/health_rls.log` |
| pool_regression | `docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/implementation_audit -e AUDIT_CONFIRM_POOL=1 api pytest tests/integration/api/audit/test_implementation_audit.py::test_staged_isolated_performance -q --tb=short --junitxml=/tmp/audit-pool.xml` | 1 | 34.881 | `evidence/pool_regression.log` |
| security_regressions | `docker compose exec -T api pytest tests/unit/audit -q --tb=short --junitxml=/tmp/audit-security.xml` | 1 | 3.798 | `evidence/security_regressions.log` |

## Counts and interpretation

- `baseline_backend`: 582 PASS, 90.62 seconds pytest time, with LIVE_INGESTION=1; captured JUnit `baseline.xml`.
- `frontend_tests`: 213 web + seven widget PASS. `browser`: five PASS, 12.3 seconds test time.
- `audit_runtime`: one PASS/two FAIL. The workflow failure was an audit fixture constructing DOCX paragraphs with the wrong shape, later corrected only in the added audit helper. The citation regression was an application failure. The performance function at this point only collected measurements; its PASS was not an acceptance result.
- `audit_workflow`: corrected workflow and 100-case retrieval evaluation PASS as a harness; the measured recall is still below target and live output is BLOCKED. One pytest function, not 100 extra pytest tests.
- `pool_regression`: one FAIL after adding a no-500 acceptance assertion, confirmed in a fresh ten-request run.
- `security_regressions`: two FAIL (rendered-source citation boundary and HTTP production embedding settings).
- Distinct final checks: 811 = 807 original + four audit functions, with 808 PASS/three FAIL. Recorded invocations including repeats: 814, with 809 PASS/five FAIL. JUnit files `audit-added.xml`, `audit-workflow.xml`, `audit-pool.xml`, `audit-security.xml` retain failed attempts and final probes.

Package-advisory checks reported zero known npm/Python package vulnerabilities. The initial static command checked application/migrations (101 source files checked by mypy). The final `audit_static` command ran full backend Ruff check, format check (162 files) and configured mypy (161 source files), all PASS. The dynamically typed integration audit harness explicitly opts out of strict type checking; unit regressions are typed. There is no whole-project coverage percentage or external penetration-test claim.

## Rerun procedure

Use the existing local development bootstrap in `docs/DEVELOPMENT.md`; provide local test database administration access as that infrastructure requires. Verify `app_env=local` and demo/hash providers first. Existing compose services should be healthy. The commands above are the actual executable recipes; Docker-dependent commands require access to the local Docker engine. Avoid concurrent tests against the same Redis test state.

For a short focused reproduction:

```powershell
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py -q --tb=short
docker compose exec -T -e AUDIT_CONFIRM_POOL=1 api pytest tests/integration/api/audit/test_implementation_audit.py::test_staged_isolated_performance -q --tb=short
docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/implementation_audit api pytest tests/integration/api/audit/test_implementation_audit.py::test_business_workflow_and_100_case_evaluation -q --tb=short
corepack pnpm --filter @acs/web exec playwright test --reporter=json
```

The first two commands are expected to fail until application fixes are separately authorized/applied. The complete four-stage workload is selected by omitting AUDIT_CONFIRM_POOL. The API test bind mount includes the dedicated audit tests and dataset; output is written inside the container under `/tmp/implementation_audit`, then copied into `docs/audit/evidence`. Re-running overwrites current per-run fixture outputs; preserve these audit artifacts before comparing later runs. The workflow test's returned local IDs are not stable between runs.

Report tooling: `docs/audit/tools/capture.py` stores redacted command output and metadata; `report.py` renders scores/findings/matrix from the audit rubric; `write_reports.py` renders the remaining reports. Review raw outcomes independently of rendered summaries. The capture wrapper originally encountered a Windows console Unicode print error after saving successful frontend-build and health/RLS command results; those subprocess exit codes and saved logs were zero. Console encoding was corrected. An earlier environment helper attempted unavailable `powershell`; it was corrected to `pwsh` before the actual checks. Neither wrapper issue is counted as an application test failure.

## Preservation and limits

SHA-256 before/after comparison of 242 pre-existing app/configuration files: zero changes (`source_preservation.json`). Only audit reports, tools, dataset and dedicated test additions were authored. Generated build/test outputs and disposable local test data are expected. No production data was touched. No real API keys were copied into evidence. Actual provider and embedding quality, production operations, cloud access policy, repository-history secret scanning and comprehensive penetration testing remain BLOCKED or NOT_TESTED as reported elsewhere.
