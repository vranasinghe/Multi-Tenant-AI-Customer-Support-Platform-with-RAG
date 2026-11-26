import { Config } from "@remotion/cli/config";

// Use the installed Chrome instead of downloading a headless shell. Override with CHROME_PATH.
Config.setBrowserExecutable(
  process.env.CHROME_PATH ?? "C:/Program Files/Google/Chrome/Application/chrome.exe",
);
Config.setChromeMode("chrome-for-testing");
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(95);
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setCrf(18);
Config.setOverwriteOutput(true);
// No licence key is set: individuals use Remotion free, and without a key a local render sends
// no usage event.
