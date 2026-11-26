import { readLoaderConfig } from "./config";
import { createRegistry, type DestroyOptions, type Handle, type Registry } from "./lifecycle";
import { mountFrame } from "./panel";

export const WIDGET_VERSION = "1.1.0";

/** Shared by every copy of this script on the page, whichever build it is. */
const SLOT = Symbol.for("acs.chat.v1");

interface PublicApi {
  readonly version: string;
  mount(options: { botKey: string; instanceKey?: string; apiOrigin?: string }): Handle | null;
  get(options: { botKey: string; instanceKey?: string; apiOrigin?: string }): Handle | null;
  destroy(
    options: { botKey: string; instanceKey?: string; apiOrigin?: string } & DestroyOptions,
  ): boolean;
}

type Page = Window & { [SLOT]?: Registry; AcsChat?: PublicApi };

/** The page's registry, created by whichever copy of the loader runs first. */
function registryFor(page: Page, api: string): Registry {
  if (page[SLOT]) return page[SLOT];
  const registry = createRegistry({
    origin: window.origin,
    now: () => Date.now(),
    nonce: () => crypto.randomUUID(),
    createFrame: () => document.createElement("iframe"),
    append: (frame) => void (document.body ?? document.documentElement).append(frame),
    listen: (fn) => window.addEventListener("message", fn),
    unlisten: (fn) => window.removeEventListener("message", fn),
    setTimeout: (fn, ms) => window.setTimeout(fn, ms),
    clearTimeout: (id) => window.clearTimeout(id),
  });
  Object.defineProperty(page, SLOT, { value: registry });
  const at = <T extends { apiOrigin?: string }>(o: T) => ({ ...o, apiOrigin: o.apiOrigin ?? api });
  // Identifiers and lifecycle only: no credential or transcript is reachable from the host page.
  page.AcsChat = Object.freeze({
    version: WIDGET_VERSION,
    mount: (o) => registry.mount(at(o)),
    get: (o) => registry.get(at(o)),
    destroy: (o) => registry.destroy(at(o)),
  } satisfies PublicApi);
  return registry;
}

const script = document.currentScript;
if (script instanceof HTMLScriptElement) {
  if (script.dataset.frameKey) mountFrame(script);
  else {
    const config = readLoaderConfig({ ...script.dataset });
    if (config.ok && window.origin !== "null") {
      const apiOrigin = new URL(script.src).origin;
      registryFor(window as Page, apiOrigin).mount({
        botKey: config.config.botKey,
        apiOrigin,
        instanceKey: script.dataset.instanceKey,
      });
    }
  }
}
