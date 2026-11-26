// Shared by the render scripts.
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";

const HERE = dirname(fileURLToPath(import.meta.url));
export const APP = resolve(HERE, "..");
export const ROOT = resolve(APP, "../..");
export const FINAL = join(ROOT, "output/video/final");

export const browser = {
  browserExecutable:
    process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe",
  chromeMode: "chrome-for-testing",
};

export const bundled = () =>
  bundle({ entryPoint: join(APP, "src/index.ts"), publicDir: join(APP, "public") });
