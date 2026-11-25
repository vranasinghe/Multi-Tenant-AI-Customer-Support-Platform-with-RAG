#!/usr/bin/env node
// End-to-end smoke test for the local Docker stack. Verifies that services can talk to each other:
//   browser → web, web → api (container network), api → Postgres/pgvector/migrations/Redis,
//   api → Celery worker via Redis (broker + result backend), and request-id propagation.
//
// Usage:  pnpm smoke            (after `docker compose up -d --build --wait`)
// Env:    WEB_URL (default http://localhost:3000), API_URL (default http://localhost:8000),
//         SMOKE_TIMEOUT_S (default 120), SMOKE_SKIP_WORKER=1 to skip the Celery round trip.
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";

const WEB_URL = process.env.WEB_URL ?? "http://localhost:3000";
const API_URL = process.env.API_URL ?? "http://localhost:8000";
const TIMEOUT_S = Number(process.env.SMOKE_TIMEOUT_S ?? 120);

let failures = 0;
const pass = (msg) => console.log(`  ✓ ${msg}`);
const fail = (msg) => {
  failures += 1;
  console.error(`  ✗ ${msg}`);
};

async function getJson(url, headers = {}) {
  const res = await fetch(url, { headers, signal: AbortSignal.timeout(5000) });
  const body = await res.json().catch(() => null);
  return { res, body };
}

async function waitFor(label, fn) {
  const deadline = Date.now() + TIMEOUT_S * 1000;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      if (await fn()) return true;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  fail(`${label} did not become ready within ${TIMEOUT_S}s ${lastError}`);
  return false;
}

console.log(`Smoke test — web ${WEB_URL}, api ${API_URL}`);

// 1. API liveness + readiness (Postgres, pgvector, migrations, Redis).
if (await waitFor("API /readyz", async () => (await getJson(`${API_URL}/readyz`)).res.ok)) {
  const { body } = await getJson(`${API_URL}/readyz`);
  for (const name of ["database", "migrations", "redis"]) {
    const check = body?.checks?.[name];
    check?.status === "ok"
      ? pass(`api → ${name}: ${check.detail}`)
      : fail(`api → ${name}: ${JSON.stringify(check)}`);
  }
  const live = await getJson(`${API_URL}/healthz`);
  live.res.ok ? pass("api /healthz") : fail(`api /healthz → ${live.res.status}`);
}

// 2. Web liveness, and web → api readiness over the container network.
if (await waitFor("web /api/health", async () => (await getJson(`${WEB_URL}/api/health`)).res.ok)) {
  pass("web /api/health");
  const requestId = `smoke-${randomUUID()}`;
  const { res, body } = await getJson(`${WEB_URL}/api/ready`, { "x-request-id": requestId });
  res.ok && body?.api?.status === "ok"
    ? pass(`web → api: ready in ${body.api.latency_ms} ms`)
    : fail(`web → api: ${res.status} ${JSON.stringify(body)}`);
  res.headers.get("x-request-id") === requestId
    ? pass("request id echoed by web")
    : fail(`request id not echoed (got ${res.headers.get("x-request-id")})`);

  const page = await fetch(WEB_URL, { signal: AbortSignal.timeout(10000) });
  const html = await page.text();
  page.ok && html.includes("Support Platform")
    ? pass("web home page renders")
    : fail(`web home page → ${page.status}`);
}

// 3. API → Celery worker round trip through Redis, with request-id propagation.
if (process.env.SMOKE_SKIP_WORKER === "1") {
  console.log("  - worker round trip skipped (SMOKE_SKIP_WORKER=1)");
} else {
  const result = spawnSync(
    "docker",
    ["compose", "exec", "-T", "api", "python", "-m", "app.cli", "check-worker", "--timeout", "20"],
    { encoding: "utf8" },
  );
  const lastLine = (result.stdout ?? "").trim().split("\n").pop() ?? "";
  result.status === 0
    ? pass(`api → worker: ${lastLine}`)
    : fail(`api → worker (exit ${result.status}): ${lastLine || result.stderr}`);
}

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log("\nAll smoke checks passed.");
