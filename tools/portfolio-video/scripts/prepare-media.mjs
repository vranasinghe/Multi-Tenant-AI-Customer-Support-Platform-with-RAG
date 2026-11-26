// Probe the recorded clips and build the media Remotion reads, without touching the originals.
//
//   npm run prepare-media
//
// Writes H.264 proxies to public/footage (Chrome cannot play the recorder's MPEG-4 Part 2),
// copies the diagrams and overlay graphics from docs/portfolio-video, turns the SRT drafts into
// JSON, and records what it found in output/video/final/qa/footage-report.json.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = resolve(HERE, "..");
const ROOT = resolve(APP, "../..");
const CLIPS = join(ROOT, "output/video/portfolio/clips");
const DOCS = join(ROOT, "docs/portfolio-video");
const QA = join(ROOT, "output/video/final/qa");
const CLI = join(APP, "node_modules/@remotion/cli/remotion-cli.js");

const EXPECTED = [
  "R01-sign-in",
  "R02-dashboard",
  "R03-create-chatbot",
  "R04-upload-and-process",
  "R05-retrieval-test",
  "R06-website-source-guard",
  "R07-playground",
  "R08-activate-and-install",
  "R09-customer-widget",
  "R10-widget-lifecycle",
  "R11-widget-mobile",
  "R12-inbox",
  "R13-analytics",
  "R14-tenant-isolation",
  "R15-dashboard-populated",
];

// Frames that must never reach a video. R08 shows the public widget key and install script before
// the recorder's mask was applied (frames 211-230). The proxy drops a margin around them.
const BLOCKED = { "R08-activate-and-install": [[204, 237]] };

const remotion = (...args) =>
  execFileSync(process.execPath, [CLI, ...args], {
    cwd: APP,
    encoding: "utf8",
    maxBuffer: 1 << 26,
  });

function probe(file) {
  const out = remotion(
    "ffprobe",
    "-v",
    "error",
    "-count_frames",
    "-show_streams",
    "-show_format",
    "-of",
    "json",
    file,
  );
  return JSON.parse(out.slice(out.indexOf("{")));
}

const sha = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");

mkdirSync(join(APP, "public/footage"), { recursive: true });
mkdirSync(join(APP, "public/diagrams"), { recursive: true });
mkdirSync(join(APP, "public/graphics"), { recursive: true });
mkdirSync(join(APP, "src/data/generated"), { recursive: true });
mkdirSync(QA, { recursive: true });

const missing = EXPECTED.filter((id) => !existsSync(join(CLIPS, `${id}.mp4`)));
if (missing.length) {
  console.error(`Missing clips: ${missing.join(", ")}`);
  console.error(
    "Re-record on a disposable stack: docs/portfolio-video/recording-scripts/README.md",
  );
  process.exit(1);
}

const report = { clips: [] };
for (const id of EXPECTED) {
  const source = join(CLIPS, `${id}.mp4`);
  const before = sha(source);
  const info = probe(source);
  const video = info.streams.find((s) => s.codec_type === "video");
  const audio = info.streams.filter((s) => s.codec_type === "audio").length;
  const proxy = join(APP, "public/footage", `${id}.mp4`);
  const blocked = BLOCKED[id] ?? [];
  const encode = (target, ...input) =>
    remotion(
      "ffmpeg",
      "-y",
      "-v",
      "error",
      ...input,
      "-an",
      "-c:v",
      "libx264",
      "-preset",
      "slow",
      "-crf",
      "16",
      "-pix_fmt",
      "yuv420p",
      "-r",
      "30",
      "-g",
      "15",
      "-movflags",
      "+faststart",
      target,
    );
  if (!blocked.length) {
    encode(proxy, "-i", source);
  } else {
    // The bundled ffmpeg has no `select` or `setpts` filter: encode each allowed range by seeking,
    // then join the parts without re-encoding.
    const total = Number(video.nb_frames);
    const keep = [];
    let from = 0;
    for (const [a, b] of blocked) {
      keep.push([from, a]);
      from = b + 1;
    }
    keep.push([from, total]);
    const parts = keep.map(([a, b], i) => {
      const part = join(APP, "public/footage", `${id}.part${i}.mp4`);
      encode(part, "-ss", (a / 30).toFixed(6), "-i", source, "-frames:v", String(b - a));
      return part;
    });
    const list = join(APP, "public/footage", `${id}.txt`);
    writeFileSync(
      list,
      parts
        .map(
          (part) => `file '${basename(part)}'
`,
        )
        .join(""),
    );
    remotion(
      "ffmpeg",
      "-y",
      "-v",
      "error",
      "-f",
      "concat",
      "-safe",
      "0",
      "-i",
      list,
      "-c",
      "copy",
      proxy,
    );
    for (const file of [...parts, list]) rmSync(file);
  }
  const out = probe(proxy).streams.find((s) => s.codec_type === "video");
  if (sha(source) !== before) throw new Error(`${id}: original changed`);
  report.clips.push({
    id,
    width: video.width,
    height: video.height,
    fps: video.r_frame_rate,
    codec: video.codec_name,
    seconds: Number(info.format.duration),
    declaredFrames: Number(video.nb_frames),
    decodedFrames: Number(video.nb_read_frames),
    audioStreams: audio,
    bytes: Number(info.format.size),
    sha256: before,
    complete: Number(video.nb_frames) === Number(video.nb_read_frames),
    blockedFrames: blocked,
    proxyFrames: Number(out.nb_read_frames),
  });
  console.log(
    `${id.padEnd(28)} ${video.width}x${video.height} ${video.codec_name} ${video.r_frame_rate} ` +
      `${Number(info.format.duration).toFixed(2)}s frames ${video.nb_read_frames}/${video.nb_frames} ` +
      `audio ${audio} -> proxy ${out.nb_read_frames}`,
  );
}
writeFileSync(join(QA, "footage-report.json"), `${JSON.stringify(report, null, 2)}\n`);

for (const [from, to] of [
  ["diagrams", "diagrams"],
  ["assets", "graphics"],
]) {
  for (const name of readdirSync(join(DOCS, from)).filter((n) => n.endsWith(".svg"))) {
    copyFileSync(join(DOCS, from, name), join(APP, "public", to, name));
  }
}

const seconds = (stamp) => {
  const [h, m, rest] = stamp.split(":");
  return Number(h) * 3600 + Number(m) * 60 + Number(rest.replace(",", "."));
};
for (const [file, name] of [
  ["video-a-showcase.en.srt", "showcase-captions"],
  ["video-b-documentary.en.srt", "documentary-captions"],
]) {
  const cues = readFileSync(join(DOCS, "subtitles", file), "utf8")
    .replace(/\r/g, "")
    .trim()
    .split("\n\n")
    .map((block) => {
      const [, times, ...lines] = block.split("\n");
      const [start, end] = times.split(" --> ").map(seconds);
      return { start, end, text: lines.join("\n") };
    });
  writeFileSync(
    join(APP, "src/data/generated", `${name}.json`),
    `${JSON.stringify(cues, null, 2)}\n`,
  );
}
await import("./excerpts.mjs");
console.log("media ready");
