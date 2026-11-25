import { readLoaderConfig } from "./config";
import { mountFrame } from "./panel";
export const WIDGET_VERSION = "1.0.0";
const script = document.currentScript;
if (script instanceof HTMLScriptElement) {
  if (script.dataset.frameKey) mountFrame(script);
  else {
    const config = readLoaderConfig({ ...script.dataset });
    if (config.ok && window.origin !== "null") {
      const api = new URL(script.src).origin;
      const instance = crypto.randomUUID();
      const frame = document.createElement("iframe");
      frame.title = "Customer support chat";
      frame.src = `${api}/widget/frame/${encodeURIComponent(config.config.botKey)}?parent_origin=${encodeURIComponent(window.origin)}&instance=${instance}`;
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin");
      frame.referrerPolicy = "no-referrer";
      Object.assign(frame.style, {
        position: "fixed",
        bottom: "16px",
        right: "16px",
        width: "76px",
        height: "76px",
        border: "0",
        zIndex: "2147483000",
        colorScheme: "normal",
      });
      window.addEventListener("message", (event) => {
        if (
          event.source !== frame.contentWindow ||
          event.origin !== api ||
          event.data?.instance !== instance
        )
          return;
        if (event.data.type === "acs-size") {
          frame.style.width = event.data.open ? "min(400px, calc(100vw - 24px))" : "76px";
          frame.style.height = event.data.open ? "min(600px, calc(100dvh - 32px))" : "76px";
          frame.style.right = event.data.left ? "auto" : "16px";
          frame.style.left = event.data.left ? "16px" : "auto";
        }
      });
      (document.body ?? document.documentElement).append(frame);
    }
  }
}
