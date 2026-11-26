// Render the final videos.
//
//   node scripts/render.mjs <showcase|documentary> [--captioned-only|--clean-only]
//   node scripts/render.mjs sample            first 25 s of the showcase, captioned, with sound
//
// The picture is rendered silent, one chapter at a time, and the mix from scripts/mix.py is added
// when the parts are joined. A cached part is reused only while the hash of everything it depends
// on (source, media, its scenes and captions, the encoder settings) is unchanged.
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { availableParallelism } from "node:os";
import { basename, join, relative } from "node:path";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { APP, browser, bundled, FINAL } from "./remotion.mjs";

const VIDEOS = {
  showcase: { composition: "PortfolioShowcaseV2", data: "showcase-v2" },
  documentary: { composition: "EngineeringDocumentary", data: "documentary" },
};
const ENCODING = {
  codec: "h264",
  crf: 18,
  pixelFormat: "yuv420p",
  imageFormat: "jpeg",
  jpegQuality: 95,
  colorSpace: "bt709",
  overwrite: true,
  muted: true,
};
const concurrency = Math.max(2, Math.floor(availableParallelism() * 0.6));

const [name, ...flags] = process.argv.slice(2);
const sample = name === "sample";
const video = VIDEOS[sample ? "showcase" : name];
if (!video) {
  console.error("Usage: node scripts/render.mjs <showcase|documentary|sample>");
  process.exit(2);
}
const label = sample ? "showcase" : name;
const ffmpeg = (args) =>
  execFileSync(
    process.execPath,
    [
      join(APP, "node_modules/@remotion/cli/remotion-cli.js"),
      "ffmpeg",
      "-y",
      "-v",
      "error",
      ...args,
    ],
    { cwd: APP, stdio: "inherit" },
  );

const walk = (folder) =>
  readdirSync(folder, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? walk(join(folder, entry.name)) : [join(folder, entry.name)],
  );

function sourceHash() {
  const hash = createHash("sha256");
  const files = [
    ...walk(join(APP, "src")).filter(
      (f) =>
        !f.endsWith(`${video.data}.json`) && !/generated.(showcase-v2|documentary)\.json$/.test(f),
    ),
    ...["footage", "diagrams", "graphics"].flatMap((d) => walk(join(APP, "public", d))),
  ].sort();
  for (const file of files) {
    hash.update(relative(APP, file));
    hash.update(readFileSync(file));
  }
  return hash.digest("hex");
}

const script = JSON.parse(
  readFileSync(join(APP, "src/data/generated", `${video.data}.json`), "utf8"),
);
const chapters = new Map();
for (const segment of script.segments) {
  const key = segment.chapter || 0;
  const chapter = chapters.get(key) ?? { from: segment.from, to: 0, segments: [] };
  chapter.to = segment.from + segment.frames - 1;
  chapter.segments.push(segment);
  chapters.set(key, chapter);
}

const serveUrl = await bundled();
const source = sourceHash();
mkdirSync(FINAL, { recursive: true });

async function picture(captions) {
  const inputProps = { variant: "final", captions };
  const options = { serveUrl, inputProps, ...browser };
  const composition = await selectComposition({ ...options, id: video.composition });
  const folder = join(FINAL, "parts", `${label}-${captions ? "captioned" : "clean"}`);
  mkdirSync(folder, { recursive: true });
  const manifest = join(folder, "manifest.json");
  const cached = existsSync(manifest) ? JSON.parse(readFileSync(manifest, "utf8")) : {};
  const render = (outputLocation, frameRange) =>
    renderMedia({ ...options, ...ENCODING, composition, outputLocation, frameRange, concurrency });
  if (sample) {
    const output = join(folder, "sample.mp4");
    await render(output, [0, 749]);
    return output;
  }
  const parts = [];
  for (const [number, chapter] of chapters) {
    const part = join(folder, `chapter-${String(number).padStart(2, "0")}.mp4`);
    const cues = script.captions.filter(
      (c) => c.end * 30 > chapter.from - 30 && c.start * 30 < chapter.to + 30,
    );
    const key = createHash("sha256")
      .update(JSON.stringify([source, ENCODING, captions, script.frames, chapter, cues]))
      .digest("hex");
    parts.push(part);
    if (existsSync(part) && cached[basename(part)]?.hash === key) {
      console.log(`reuse ${basename(part)}`);
      continue;
    }
    const started = Date.now();
    await render(part, [chapter.from, chapter.to]);
    cached[basename(part)] = { hash: key, frames: chapter.to - chapter.from + 1 };
    writeFileSync(manifest, JSON.stringify(cached, null, 2));
    console.log(`${basename(part)} ${Math.round((Date.now() - started) / 1000)}s`);
  }
  const list = join(folder, "parts.txt");
  writeFileSync(list, parts.map((part) => `file '${basename(part)}'\n`).join(""));
  const joined = join(folder, "picture.mp4");
  ffmpeg(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", joined]);
  rmSync(list);
  return joined;
}

const variants = sample
  ? [true]
  : flags.includes("--captioned-only")
    ? [true]
    : flags.includes("--clean-only")
      ? [false]
      : [false, true];

for (const captions of variants) {
  const silent = await picture(captions);
  const output = sample
    ? join(FINAL, "parts", "sample-narrated.mp4")
    : join(FINAL, `${label}-final${captions ? "-captioned" : ""}.mp4`);
  ffmpeg([
    "-i",
    silent,
    "-i",
    join(APP, "narration/audio", `${label}-mix.wav`),
    "-map",
    "0:v:0",
    "-map",
    "1:a:0",
    "-c:v",
    "copy",
    "-c:a",
    "aac",
    "-b:a",
    "256k",
    "-ar",
    "48000",
    "-ac",
    "2",
    "-shortest",
    "-movflags",
    "+faststart",
    output,
  ]);
  console.log(`${output} ${(statSync(output).size / 1e6).toFixed(1)} MB`);
}
