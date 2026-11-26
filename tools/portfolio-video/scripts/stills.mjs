// Still frames for review.
//
//   node scripts/stills.mjs <CompositionId> <folder under output/video/final/qa> <frame...>
//   node scripts/stills.mjs PortfolioShowcaseV2 stills-v2 75 400 900
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { openBrowser, renderStill, selectComposition } from "@remotion/renderer";
import { browser, bundled, FINAL } from "./remotion.mjs";

const [id, folder, ...rest] = process.argv.slice(2);
if (!id || !folder || !rest.length) {
  console.error("Usage: node scripts/stills.mjs <CompositionId> <folder> <frame...>");
  process.exit(2);
}
const out = join(FINAL, "qa", folder);
mkdirSync(out, { recursive: true });

const serveUrl = await bundled();
const chrome = await openBrowser("chrome", browser);
const inputProps = { variant: "preview", captions: true };
const options = { serveUrl, inputProps, puppeteerInstance: chrome, ...browser };
const composition = await selectComposition({ ...options, id });
for (const value of rest) {
  const frame = Math.min(Number(value), composition.durationInFrames - 1);
  const name = `${String(frame).padStart(5, "0")}.png`;
  await renderStill({ ...options, composition, frame, output: join(out, name) });
}
console.log(`${rest.length} stills in ${out}`);
await chrome.close({ silent: true });
