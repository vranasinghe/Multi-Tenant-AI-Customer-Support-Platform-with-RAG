// Fails the build if the loader exceeds its gzip budget (PRD FR-WID-1: < 10 KB).
import { readFileSync, mkdirSync, copyFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET_BYTES = 10 * 1024;
const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const file = fileURLToPath(new URL("../dist/loader.js", import.meta.url));
const gzipped = gzipSync(readFileSync(file)).length;

if (gzipped > BUDGET_BYTES) {
  console.error(`loader.js is ${gzipped} B gzipped; budget is ${BUDGET_BYTES} B.`);
  process.exit(1);
}
console.log(`loader.js: ${gzipped} B gzipped (budget ${BUDGET_BYTES} B)`);

const target = new URL("../../../services/api/widget_assets/v1/", import.meta.url);
mkdirSync(target, { recursive: true });
copyFileSync(file, new URL("loader.js", target));

writeFileSync(
  new URL("manifest.json", target),
  JSON.stringify({ version, file: "loader.js", gzipBytes: gzipped }, null, 2) + "\n",
);
