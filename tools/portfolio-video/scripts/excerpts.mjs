// Copy exact lines from repository source and stored test artifacts into the data the evidence
// panels render. Nothing on those panels is typed by hand.
//
//   node scripts/excerpts.mjs        (also run by prepare-media)
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const APP = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = resolve(APP, "../..");
const EVIDENCE = "docs/mvp-improvement/evidence/MILESTONE-A-FINAL";

// [file, first line, last line]
const CODE = {
  pool: ["services/api/app/services/chat_controls.py", 121, 136],
  citation: ["services/api/app/rag/retrieval.py", 271, 281],
  transport: ["services/api/app/core/provider_urls.py", 10, 25],
  proxy: ["services/api/app/core/proxy_trust.py", 41, 49],
  parser: ["services/api/app/rag/parser_process.py", 62, 75],
  fencing: ["services/api/app/rag/pipeline.py", 158, 170],
  storage: ["services/api/app/rag/originals.py", 59, 74],
  inbox: ["services/api/app/services/inbox.py", 52, 69],
  widget: ["services/api/app/services/public_view.py", 29, 46],
  scheduler: ["services/api/app/workers/celery_app.py", 46, 53],
  backup: ["deploy/restore.sh", 43, 49],
  ci: [".github/workflows/ci.yml", 73, 80],
};

// [file, regex of lines to keep (null keeps all), maximum lines]
const ARTIFACTS = {
  capacity: [
    `${EVIDENCE}/final/suite-data/capacity-100.json`,
    /"(concurrency|requests|success|rejected|failed|successful_p95_ms|rejected_p95_ms)"/,
    7,
  ],
  mutantsTransport: [`${EVIDENCE}/verification/mutants-all.json`, /"AUD-03|20 failed|15 failed/, 4],
  mutantsProxy: [`${EVIDENCE}/verification/mutants-all.json`, /"AUD-04|37 failed/, 2],
  mutantsAll: [`${EVIDENCE}/verification/mutants-all.json`, /^ {2}"AUD-|passed in/, 16],
  proxyTests: [`${EVIDENCE}/final/ci/runtime-proxy.log`, /passed/, 2],
  hardLimit: [`${EVIDENCE}/final/suite-data/hard-limit.json`, null, 6],
  workerRestart: [`${EVIDENCE}/final/suite-data/worker-restart.json`, null, 6],
  busySlots: [`${EVIDENCE}/final/suite-data/maintenance-busy-slots.json`, null, 3],
  restore: [`${EVIDENCE}/final/ci/restore/summary.log`, /backup_seconds|restored application/, 3],
  restoreApp: [`${EVIDENCE}/final/ci/restore/application.log`, /restored application/, 1],
  backend: [`${EVIDENCE}/final/backend-full.log`, /passed|tests=/, 3],
  web: [`${EVIDENCE}/final/web-2.log`, /Tests |loader\.js:/, 3],
  browser: [`${EVIDENCE}/final/browser.log`, /passed/, 2],
  recall: [
    `${EVIDENCE}/final/suite-data/rag_metrics.json`,
    /"(dataset_size|answerable_cases|recall_at_5_hits|recall_at_5|embedder|provider|live_status)"/,
    7,
  ],
  widgetDedup: [`${EVIDENCE}/verification/mutant-widget-dedup.log`, /\d+ failed \| \d+ passed/, 1],
  cursorMutant: [
    `${EVIDENCE}/verification/mutants-AUD-06-cursor-not-scoped.json`,
    /"AUD-06|"file"|"killed"|passed in/,
    4,
  ],
};

const lines = (file) =>
  readFileSync(join(ROOT, file), "utf8")
    .replace(/\r/g, "")
    .replace(/\x1b\[[0-9;]*m/g, "")
    .split("\n");

const out = { code: {}, artifacts: {} };
for (const [key, [file, first, last]] of Object.entries(CODE)) {
  out.code[key] = { file, first, last, lines: lines(file).slice(first - 1, last) };
}
for (const [key, [file, keep, max]] of Object.entries(ARTIFACTS)) {
  const all = lines(file).filter((line) => line.trim() && (!keep || keep.test(line)));
  const chosen = key === "backend" || key === "browser" ? all.slice(-max) : all.slice(0, max);
  if (!chosen.length) throw new Error(`${key}: nothing matched in ${file}`);
  out.artifacts[key] = { file, lines: chosen };
}

const text = JSON.stringify(out, null, 2);
// A local user path must never reach a frame.
if (/[A-Z]:\\\\|\/Users\/|\\\\Users\\\\/.test(text))
  throw new Error("an excerpt contains a local path");
mkdirSync(join(APP, "src/data/generated"), { recursive: true });
writeFileSync(join(APP, "src/data/generated/excerpts.json"), `${text}\n`);
console.log(
  `excerpts: ${Object.keys(out.code).length} source, ${Object.keys(out.artifacts).length} artifact`,
);
