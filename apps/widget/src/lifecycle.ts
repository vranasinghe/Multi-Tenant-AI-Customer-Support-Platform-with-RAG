import { PUBLIC_KEY_PATTERN } from "./config";

// Host-page side of the widget: which instances exist and what each one owns. The conversation,
// its credentials and every request live inside the frame; removing the frame ends them.

export const INSTANCE_KEY_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
export const DEFAULT_INSTANCE = "default";
/** A frame that has said nothing for this long failed to load and may be replaced. */
const LOAD_PATIENCE_MS = 15_000;
const FORGET_PATIENCE_MS = 5_000;

export interface MountOptions {
  botKey: string;
  apiOrigin: string;
  instanceKey?: string;
}

export interface DestroyOptions {
  /** Also remove this instance's resume entry from the browser. Nothing is deleted server-side. */
  forget?: boolean;
}

export interface Handle {
  readonly botKey: string;
  readonly instanceKey: string;
  destroy(options?: DestroyOptions): boolean;
}

export interface Host {
  origin: string;
  now(): number;
  nonce(): string;
  createFrame(): HTMLIFrameElement;
  append(frame: HTMLIFrameElement): void;
  listen(fn: (event: MessageEvent) => void): void;
  unlisten(fn: (event: MessageEvent) => void): void;
  setTimeout(fn: () => void, ms: number): number;
  clearTimeout(id: number): void;
}

interface Instance {
  handle: Handle;
  frame: HTMLIFrameElement;
  created: number;
  ready: boolean;
  destroy(options?: DestroyOptions): void;
}

export interface Registry {
  mount(options: MountOptions): Handle | null;
  get(options: MountOptions): Handle | null;
  destroy(options: MountOptions & DestroyOptions): boolean;
}

export function createRegistry(host: Host): Registry {
  const instances = new Map<string, Instance>();
  const identify = (o: MountOptions) =>
    [o.apiOrigin, host.origin, o.botKey, o.instanceKey ?? DEFAULT_INSTANCE].join("|");

  function create(id: string, botKey: string, api: string, instanceKey: string): Instance {
    const nonce = host.nonce();
    const frame = host.createFrame();
    let removed = false;
    let forgetting = false;
    let timer: number | undefined;

    const query = new URLSearchParams({ parent_origin: host.origin, instance: nonce });
    if (instanceKey !== DEFAULT_INSTANCE) query.set("instance_key", instanceKey);
    frame.title = "Customer support chat";
    frame.src = `${api}/widget/frame/${encodeURIComponent(botKey)}?${query.toString()}`;
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

    function remove() {
      if (removed) return;
      removed = true;
      host.unlisten(onMessage);
      if (timer !== undefined) host.clearTimeout(timer);
      frame.remove();
    }
    const askToForget = () =>
      frame.contentWindow?.postMessage({ type: "acs-forget", instance: nonce }, api);

    function onMessage(event: MessageEvent) {
      // Only this instance's own frame, from the API origin, with its per-mount nonce.
      if (removed || event.source !== frame.contentWindow || event.origin !== api) return;
      const data = event.data as { instance?: unknown; type?: unknown; open?: unknown } | null;
      if (typeof data !== "object" || data === null || data.instance !== nonce) return;
      if (data.type === "acs-forgotten" && forgetting) return remove();
      if (data.type !== "acs-size" || typeof data.open !== "boolean") return;
      const first = !instance.ready;
      instance.ready = true;
      if (forgetting) {
        if (first) askToForget();
        return;
      }
      const left = (data as { left?: unknown }).left === true;
      frame.style.width = data.open ? "min(400px, calc(100vw - 24px))" : "76px";
      frame.style.height = data.open ? "min(600px, calc(100dvh - 32px))" : "76px";
      frame.style.right = left ? "auto" : "16px";
      frame.style.left = left ? "16px" : "auto";
    }

    const instance: Instance = {
      frame,
      created: host.now(),
      ready: false,
      handle: Object.freeze({
        botKey,
        instanceKey,
        destroy: (options?: DestroyOptions) => {
          if (instances.get(id) !== instance) return false;
          instances.delete(id);
          instance.destroy(options);
          return true;
        },
      }),
      destroy(options) {
        if (!options?.forget) return remove();
        // The resume entry lives in the frame's origin: only the frame can remove it.
        forgetting = true;
        frame.style.display = "none";
        timer = host.setTimeout(remove, FORGET_PATIENCE_MS);
        if (instance.ready) askToForget();
      },
    };
    host.listen(onMessage);
    host.append(frame);
    return instance;
  }

  function mount(options: MountOptions): Handle | null {
    const instanceKey = options.instanceKey ?? DEFAULT_INSTANCE;
    if (!PUBLIC_KEY_PATTERN.test(options.botKey) || !INSTANCE_KEY_PATTERN.test(instanceKey)) {
      return null;
    }
    const id = identify(options);
    const existing = instances.get(id);
    if (existing) {
      const failed = !existing.ready && host.now() - existing.created > LOAD_PATIENCE_MS;
      if (existing.frame.isConnected && !failed) return existing.handle;
      existing.handle.destroy();
    }
    const instance = create(id, options.botKey, options.apiOrigin, instanceKey);
    instances.set(id, instance);
    return instance.handle;
  }

  return {
    mount,
    get: (options) => instances.get(identify(options))?.handle ?? null,
    destroy: (options) =>
      instances.get(identify(options))?.handle.destroy({ forget: options.forget }) ?? false,
  };
}
