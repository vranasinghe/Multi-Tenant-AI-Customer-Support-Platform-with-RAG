import { describe, expect, it } from "vitest";

import { createRegistry, type Host } from "./lifecycle";

const KEY = "pk_live_abcdefgh1234";
const OTHER = "pk_live_zyxwvuts9876";
const API = "https://api.example.test";

/** A host page that records exactly what the registry owns. */
function fakeHost() {
  const listeners = new Set<(event: unknown) => void>();
  const frames = new Set<ReturnType<typeof makeFrame>>();
  const timers = new Map<number, () => void>();
  let next = 0;
  let now = 0;
  function makeFrame() {
    const posted: { data: unknown; origin: string }[] = [];
    const frame = {
      title: "",
      src: "",
      referrerPolicy: "",
      style: {} as Record<string, string>,
      isConnected: false,
      attributes: {} as Record<string, string>,
      posted,
      contentWindow: {
        postMessage: (data: unknown, origin: string) => posted.push({ data, origin }),
      },
      setAttribute(name: string, value: string) {
        frame.attributes[name] = value;
      },
      remove() {
        frame.isConnected = false;
        frames.delete(frame);
      },
    };
    return frame;
  }
  const host: Host = {
    origin: "https://shop.example.test",
    now: () => now,
    nonce: () => `nonce-${++next}`,
    createFrame: () => makeFrame() as never,
    append: (frame) => {
      const fake = frame as unknown as ReturnType<typeof makeFrame>;
      fake.isConnected = true;
      frames.add(fake);
    },
    listen: (fn) => void listeners.add(fn as never),
    unlisten: (fn) => void listeners.delete(fn as never),
    setTimeout: (fn) => {
      timers.set(++next, fn);
      return next;
    },
    clearTimeout: (id) => void timers.delete(id),
  };
  return {
    host,
    listeners,
    frames,
    timers,
    advance: (ms: number) => (now += ms),
    /** Deliver a message as the browser would to every live listener. */
    deliver: (event: unknown) => [...listeners].forEach((fn) => fn(event)),
    runTimers: () => {
      for (const [id, fn] of [...timers]) {
        timers.delete(id);
        fn();
      }
    },
  };
}

type Fake = ReturnType<typeof fakeHost>;
const only = (fake: Fake) => [...fake.frames][0]!;
const nonceOf = (fake: Fake) => new URL(only(fake).src).searchParams.get("instance");
const from = (fake: Fake, data: Record<string, unknown>, overrides: object = {}) => ({
  source: only(fake).contentWindow,
  origin: API,
  data: { instance: nonceOf(fake), ...data },
  ...overrides,
});
const mount = { botKey: KEY, apiOrigin: API };

describe("widget registry", () => {
  it("keeps one instance for repeated mounts of the same identity", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);

    const first = registry.mount(mount);
    const second = registry.mount(mount);

    expect(second).toBe(first);
    expect(fake.frames.size).toBe(1);
    expect(fake.listeners.size).toBe(1);
    expect(only(fake).src).toContain(`/widget/frame/${KEY}?`);
    expect(only(fake).attributes.sandbox).toBe("allow-scripts allow-same-origin");
    expect(only(fake).referrerPolicy).toBe("no-referrer");
    expect(Object.keys(first!).sort()).toEqual(["botKey", "destroy", "instanceKey"]);
  });

  it("separates keys, explicit instance keys and API origins", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);

    registry.mount(mount);
    registry.mount({ ...mount, botKey: OTHER });
    registry.mount({ ...mount, instanceKey: "footer" });
    registry.mount({ ...mount, apiOrigin: "https://api.other.test" });

    expect(fake.frames.size).toBe(4);
    const urls = [...fake.frames].map((f) => new URL(f.src));
    expect(new Set(urls.map((u) => u.searchParams.get("instance"))).size).toBe(4);
    expect(urls.filter((u) => u.searchParams.has("instance_key")).length).toBe(1);
  });

  it.each([
    { botKey: "sk_live_secret", apiOrigin: API },
    { botKey: KEY, apiOrigin: API, instanceKey: "../x" },
    { botKey: KEY, apiOrigin: API, instanceKey: "x".repeat(33) },
  ])("refuses invalid options and stays usable: %o", (options) => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);

    expect(registry.mount(options)).toBeNull();
    expect(fake.frames.size + fake.listeners.size).toBe(0);
    expect(registry.mount(mount)).not.toBeNull();
  });

  it("releases everything on destroy, twice safely, over many cycles", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    for (let cycle = 0; cycle < 30; cycle++) {
      const handle = registry.mount(mount)!;
      expect([fake.frames.size, fake.listeners.size]).toEqual([1, 1]);
      expect(handle.destroy()).toBe(true);
      expect(handle.destroy()).toBe(false);
      expect(registry.destroy(mount)).toBe(false);
    }

    expect([fake.frames.size, fake.listeners.size, fake.timers.size]).toEqual([0, 0, 0]);
    expect(registry.get(mount)).toBeNull();
  });

  it("does not let an old handle destroy a newer instance", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    const old = registry.mount(mount)!;
    old.destroy();
    registry.mount(mount);

    expect(old.destroy()).toBe(false);
    expect(fake.frames.size).toBe(1);
  });

  it("replaces an instance the host page removed, or one that never became ready", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    registry.mount(mount);
    only(fake).remove();
    registry.mount(mount);
    expect([fake.frames.size, fake.listeners.size]).toEqual([1, 1]);

    const stuck = nonceOf(fake);
    fake.advance(14_000);
    registry.mount(mount);
    expect(nonceOf(fake)).toBe(stuck); // still loading: not replaced
    fake.advance(2_000);
    registry.mount(mount);
    expect(nonceOf(fake)).not.toBe(stuck); // failed to load: replaced

    fake.deliver(from(fake, { type: "acs-size", open: false }));
    const ready = nonceOf(fake);
    fake.advance(60_000);
    registry.mount(mount);
    expect(nonceOf(fake)).toBe(ready);
    expect([fake.frames.size, fake.listeners.size]).toEqual([1, 1]);
  });

  it("resizes only for its own frame's well-formed messages", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    registry.mount(mount);
    const open = { type: "acs-size", open: true, left: true };
    for (const forged of [
      from(fake, open, { source: {} }),
      from(fake, open, { origin: "https://evil.test" }),
      from(fake, { ...open, instance: "other" }),
      from(fake, { ...open, open: "yes" }),
      { source: only(fake).contentWindow, origin: API, data: null },
      { source: only(fake).contentWindow, origin: API, data: "acs-size" },
    ]) {
      fake.deliver(forged);
      expect(only(fake).style.width).toBe("76px");
    }

    fake.deliver(from(fake, open));

    expect(only(fake).style.width).toBe("min(400px, calc(100vw - 24px))");
    expect(only(fake).style.left).toBe("16px");
  });

  it("ignores messages that arrive after destroy", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    registry.mount(mount);
    const frame = only(fake);
    const late = from(fake, { type: "acs-size", open: true });
    const listener = [...fake.listeners][0]!;
    registry.destroy(mount);

    listener(late);

    expect(frame.style.width).toBe("76px");
  });

  it("asks a ready frame to forget before removing it", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    registry.mount(mount);
    fake.deliver(from(fake, { type: "acs-size", open: false }));
    const frame = only(fake);
    const nonce = nonceOf(fake);

    expect(registry.destroy({ ...mount, forget: true })).toBe(true);

    expect(frame.posted).toEqual([{ data: { type: "acs-forget", instance: nonce }, origin: API }]);
    expect(frame.style.display).toBe("none");
    expect(registry.get(mount)).toBeNull();
    fake.deliver({
      source: frame.contentWindow,
      origin: API,
      data: { type: "acs-forgotten", instance: nonce },
    });
    expect([fake.frames.size, fake.listeners.size, fake.timers.size]).toEqual([0, 0, 0]);
  });

  it("waits for a loading frame before asking it to forget, and gives up eventually", () => {
    const fake = fakeHost();
    const registry = createRegistry(fake.host);
    registry.mount(mount);
    const frame = only(fake);
    registry.destroy({ ...mount, forget: true });
    expect(frame.posted).toEqual([]);

    fake.deliver({
      source: frame.contentWindow,
      origin: API,
      data: {
        type: "acs-size",
        instance: new URL(frame.src).searchParams.get("instance"),
        open: false,
      },
    });
    expect(frame.posted).toHaveLength(1);

    fake.runTimers(); // no answer
    expect([fake.frames.size, fake.listeners.size, fake.timers.size]).toEqual([0, 0, 0]);
  });
});
