import { createServer, type Server } from "node:http";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { API_URL, WEB_ORIGIN, signUpVerified } from "./helpers";

// AUD-07. Real loader and widget bundle, real API. All content synthetic. The public widget
// limits stay as they are: checks that only concern the host page use a stand-in frame document.

const SITE = "http://localhost:3103";
const HEADERS = { "X-Requested-With": "platform", Origin: WEB_ORIGIN };
const SHOTS = process.env.E2E_SHOT_DIR ?? "test-results";
const FRAME = 'iframe[title="Customer support chat"]';

let server: Server;
let cookies: Awaited<ReturnType<BrowserContext["cookies"]>>;
let org = "";
let bot: { id: string; public_key: string };
let other: { id: string; public_key: string };

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ browser, playwright }) => {
  server = createServer((_req, res) => {
    res.setHeader("Content-Type", "text/html");
    res.end(
      '<!doctype html><meta name="viewport" content="width=device-width"><title>Site</title>',
    );
  });
  await new Promise<void>((resolve) => server.listen(3103, "127.0.0.1", resolve));

  const context = await browser.newContext({ baseURL: WEB_ORIGIN });
  const request = await playwright.request.newContext();
  const page = await context.newPage();
  org = await signUpVerified(page, request);
  const api = `${API_URL}/api/v1${org}/chatbots`;
  const make = async (name: string) => {
    const created = await page.request.post(api, {
      headers: HEADERS,
      data: { name, status: "active" },
    });
    expect(created.status()).toBe(201);
    const made = (await created.json()) as { id: string; public_key: string };
    for (const origin of [SITE, WEB_ORIGIN]) {
      await page.request.post(`${api}/${made.id}/domains`, { headers: HEADERS, data: { origin } });
    }
    const config = (await (
      await page.request.get(`${api}/${made.id}/widget-config`, { headers: HEADERS })
    ).json()) as { domains: { id: string }[] };
    for (const domain of config.domains) {
      await page.request.post(`${api}/${made.id}/domains/${domain.id}/verify`, {
        headers: HEADERS,
      });
    }
    return made;
  };
  bot = await make("Lifecycle Bot");
  other = await make("Second Bot");
  const uploaded = await page.request.post(`${api}/${bot.id}/documents?filename=returns.txt`, {
    headers: { ...HEADERS, "Content-Type": "text/plain" },
    data: Buffer.from("Returns are allowed within thirty days of delivery with a receipt."),
  });
  const document = (await uploaded.json()) as { id: string };
  await expect
    .poll(
      async () =>
        (
          (await (await page.request.get(`${api}/${bot.id}/documents/${document.id}`)).json()) as {
            status: string;
          }
        ).status,
      { timeout: 60_000 },
    )
    .toBe("ready");
  cookies = await context.cookies();
  await request.dispose();
  await context.close();
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

type Api = {
  mount: (o: { botKey: string; instanceKey?: string }) => unknown;
  get: (o: { botKey: string; instanceKey?: string }) => unknown;
  destroy: (o: { botKey: string; instanceKey?: string; forget?: boolean }) => boolean;
};
declare global {
  interface Window {
    AcsChat?: Api;
    __messageListeners?: () => number;
  }
}

/** Count the host page's live `message` listeners, installed before any script runs. */
async function watchListeners(page: Page) {
  await page.addInitScript(() => {
    const live = new Set<unknown>();
    const add = window.addEventListener.bind(window);
    const remove = window.removeEventListener.bind(window);
    window.addEventListener = ((type: string, fn: EventListener, options?: boolean) => {
      if (type === "message") live.add(fn);
      add(type, fn, options);
    }) as typeof window.addEventListener;
    window.removeEventListener = ((type: string, fn: EventListener, options?: boolean) => {
      if (type === "message") live.delete(fn);
      remove(type, fn, options);
    }) as typeof window.removeEventListener;
    window.__messageListeners = () => live.size;
  });
}

/** Replace the frame document with an inert stand-in: host-page behaviour only. */
async function standInFrames(page: Page) {
  await page.route(`${API_URL}/widget/frame/**`, (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<!doctype html><script>const q=new URLSearchParams(location.search);
        parent.postMessage({type:"acs-size",instance:q.get("instance"),open:false},q.get("parent_origin"));</script>`,
    }),
  );
}

async function embed(page: Page, key: string, instanceKey?: string) {
  await page.evaluate(
    ({ api, key, instanceKey }) =>
      new Promise<void>((resolve) => {
        const script = document.createElement("script");
        script.src = `${api}/widget/v1/loader.js`;
        script.dataset.botKey = key;
        if (instanceKey) script.dataset.instanceKey = instanceKey;
        script.onload = () => resolve();
        document.body.append(script);
      }),
    { api: API_URL, key, instanceKey },
  );
}

const frames = (page: Page) => page.locator(FRAME);
const destroy = (
  page: Page,
  botKey: string,
  extra: { instanceKey?: string; forget?: boolean } = {},
) => page.evaluate((o) => window.AcsChat!.destroy(o), { botKey, ...extra });
const listeners = (page: Page) => page.evaluate(() => window.__messageListeners!());
const widgetOf = (page: Page, key: string, nth = 0) =>
  page.frameLocator(`iframe[src*="/widget/frame/${key}"]`).nth(nth);

async function ask(widget: ReturnType<typeof widgetOf>, question: string) {
  await widget.getByLabel("Your question").fill(question);
  await widget.getByRole("button", { name: "Send", exact: true }).click();
}

async function open(widget: ReturnType<typeof widgetOf>) {
  await widget.getByRole("button", { name: "Open support chat" }).click();
  await expect(widget.getByRole("status").first()).toHaveText("");
}

test("repeated installs make one instance, and destroy releases it completely", async ({
  page,
}) => {
  await watchListeners(page);
  await standInFrames(page);
  await page.goto(SITE);
  const requests: string[] = [];
  page.on("request", (r) => r.url().includes("/widget/frame/") && requests.push(r.url()));

  await Promise.all([embed(page, bot.public_key), embed(page, bot.public_key)]);
  await embed(page, bot.public_key);
  await expect(frames(page)).toHaveCount(1);
  await expect.poll(() => requests.length).toBe(1);
  expect(await listeners(page)).toBe(1);

  expect(await destroy(page, bot.public_key)).toBe(true);
  expect(await destroy(page, bot.public_key)).toBe(false);
  await expect(frames(page)).toHaveCount(0);
  expect(await listeners(page)).toBe(0);

  for (let cycle = 0; cycle < 25; cycle++) {
    await page.evaluate((botKey) => {
      window.AcsChat!.mount({ botKey });
      window.AcsChat!.mount({ botKey });
    }, bot.public_key);
    await expect(frames(page)).toHaveCount(1);
    await destroy(page, bot.public_key);
  }
  await expect(frames(page)).toHaveCount(0);
  expect(await listeners(page)).toBe(0);

  await embed(page, bot.public_key); // a script tag added again after teardown mounts again
  await expect(frames(page)).toHaveCount(1);
  await page.evaluate(() => document.querySelector("iframe")!.remove()); // removed by the host
  await page.evaluate((botKey) => window.AcsChat!.mount({ botKey }), bot.public_key);
  await expect(frames(page)).toHaveCount(1);
  expect(await listeners(page)).toBe(1);
});

test("different keys and explicit instance keys stay independent", async ({ page }) => {
  await watchListeners(page);
  await standInFrames(page);
  await page.goto(SITE);
  await embed(page, bot.public_key);
  await embed(page, other.public_key);
  await embed(page, bot.public_key, "second");
  await embed(page, bot.public_key, "second");
  await embed(page, bot.public_key, "../not valid");
  await expect(frames(page)).toHaveCount(3);
  expect(await listeners(page)).toBe(3);

  // Only the frame itself may move its widget: forged messages from the page are ignored.
  const width = () =>
    frames(page)
      .first()
      .evaluate((f) => (f as HTMLIFrameElement).style.width);
  await page.evaluate(() => {
    const instance = new URL(document.querySelector("iframe")!.src).searchParams.get("instance");
    for (const data of [
      { type: "acs-size", instance, open: true },
      { type: "acs-size", instance: "wrong", open: true },
      "text",
      null,
      { type: "acs-forgotten", instance },
    ]) {
      window.postMessage(data, location.origin);
    }
  });
  await page.waitForTimeout(100);
  expect(await width()).toBe("76px");

  await destroy(page, other.public_key);
  await expect(frames(page)).toHaveCount(2);
  await destroy(page, bot.public_key, { instanceKey: "second" });
  await expect(frames(page)).toHaveCount(1);
  expect(await listeners(page)).toBe(1);
});

test("a visitor resumes after reload and remount, and can start over", async ({ page }) => {
  await page.goto(SITE);
  await embed(page, bot.public_key);
  await embed(page, bot.public_key);
  await expect(frames(page)).toHaveCount(1);
  const widget = widgetOf(page, bot.public_key);
  await open(widget);
  await ask(widget, "Are returns allowed within thirty days?");
  await expect(widget.getByRole("log")).toContainText("Demo response");
  await expect(widget.getByRole("log")).toContainText("returns.txt");
  await shot(page, "widget-answer");

  await page.reload();
  await embed(page, bot.public_key);
  await open(widget);
  await expect(widget.getByRole("log")).toContainText("thirty days?");

  await destroy(page, bot.public_key);
  await embed(page, bot.public_key);
  await open(widget);
  await expect(widget.getByRole("log")).toContainText("thirty days?"); // teardown keeps resume

  await embed(page, bot.public_key, "second");
  const second = widgetOf(page, bot.public_key, 1);
  await widget.getByRole("button", { name: "Close support chat" }).click();
  await open(second);
  await expect(second.getByRole("log")).not.toContainText("thirty days?");
  await second.getByRole("button", { name: "Close support chat" }).click();
  await destroy(page, bot.public_key, { instanceKey: "second" });

  await destroy(page, bot.public_key, { forget: true });
  await expect(frames(page)).toHaveCount(0);
  await embed(page, bot.public_key);
  await open(widget);
  await expect(widget.getByRole("log")).not.toContainText("thirty days?");
});

const shot = (page: Page, name: string) => page.screenshot({ path: `${SHOTS}/${name}.png` });

test("destroying mid-answer stops the stream, and the widget works again", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(SITE);
  await embed(page, bot.public_key);
  const answering = widgetOf(page, bot.public_key);
  await open(answering);
  await answering.getByRole("button", { name: "New chat" }).click();
  await expect(answering.getByRole("status").first()).toHaveText("");
  await page.exposeFunction("stopNow", () => destroy(page, bot.public_key));
  await answering.locator("#log").evaluate((log) => {
    new MutationObserver((_records, observer) => {
      if (!log.textContent!.includes("Demo")) return;
      observer.disconnect();
      void (window as unknown as { stopNow: () => Promise<boolean> }).stopNow();
    }).observe(log, { subtree: true, childList: true, characterData: true });
  });
  await ask(answering, "Are returns allowed with a receipt?");
  await expect(frames(page)).toHaveCount(0);

  await page.context().addCookies(cookies);
  const base = `${API_URL}/api/v1${org}/conversations`;
  let status = "";
  await expect
    .poll(async () => {
      const list = (await (
        await page.request.get(`${base}?channel=widget&q=receipt%3F`)
      ).json()) as { data: { id: string }[] };
      if (!list.data[0]) return "missing";
      const detail = (await (await page.request.get(`${base}/${list.data[0].id}`)).json()) as {
        messages: { role: string; status: string }[];
      };
      status = detail.messages.at(-1)!.status;
      return status;
    })
    .toMatch(/interrupted|complete/);
  console.log(`destroy-mid-stream: stored message status=${status}`);

  await embed(page, bot.public_key);
  await open(answering);
  await ask(answering, "Are returns allowed within thirty days again?");
  await expect(answering.getByRole("log")).toContainText("Demo response");
  expect(errors).toEqual([]);
});

test("public responses carry only what the widget needs", async ({ page }) => {
  const bodies: string[] = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (url.includes("/public/v1/")) {
      try {
        bodies.push(`${response.request().method()} ${url}\n${await response.text()}`);
      } catch {
        /* preflight */
      }
    }
  });
  await page.goto(SITE);
  await embed(page, bot.public_key);
  const widget = widgetOf(page, bot.public_key);
  await open(widget);
  await widget.getByRole("button", { name: "New chat" }).click();
  await expect(widget.getByRole("status").first()).toHaveText("");
  await ask(widget, "Are returns allowed with proof?");
  await expect(widget.getByRole("button", { name: "Helpful", exact: true })).toBeVisible(); // done
  await expect.poll(() => bodies.some((b) => b.includes("event: done"))).toBe(true);
  await page.reload();
  await embed(page, bot.public_key);
  await open(widget);
  await expect(widget.getByRole("log")).toContainText("proof?");
  await expect.poll(() => bodies.filter((b) => b.startsWith("GET")).length).toBeGreaterThan(1);

  const all = bodies.join("\n\n");
  const fs = await import("node:fs");
  fs.writeFileSync(
    `${SHOTS}/public-responses.txt`,
    all.replace(/"(token|resume_token)":"[^"]+"/g, '"$1":"[REDACTED]"'),
  );
  for (const forbidden of [
    "input_tokens",
    "output_tokens",
    "estimated_cost_usd",
    "usage_estimated",
    "document_id",
    "chunk_id",
    "latency_ms",
    "error_code",
    "conversation_id",
  ]) {
    expect(all, forbidden).not.toContain(forbidden);
  }
  expect(all).toContain("returns.txt");

  await page.context().addCookies(cookies);
  const base = `${API_URL}/api/v1${org}/conversations`;
  const list = (await (await page.request.get(`${base}?q=proof%3F`)).json()) as {
    data: { id: string }[];
  };
  const dashboard = await (await page.request.get(`${base}/${list.data[0]!.id}`)).text();
  for (const kept of ["input_tokens", "estimated_cost_usd", "document_id", "chunk_id"]) {
    expect(dashboard, kept).toContain(kept);
  }
});

test("keyboard and a 390px screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(SITE);
  await embed(page, bot.public_key);
  const widget = widgetOf(page, bot.public_key);
  const launcher = widget.getByRole("button", { name: "Open support chat" });
  await launcher.focus();
  await page.keyboard.press("Enter");
  await expect(widget.getByLabel("Your question")).toBeFocused();
  const box = (await frames(page).boundingBox())!;
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(widget.getByRole("status").first()).toHaveText("");
  await shot(page, "widget-390px");
  await widget.getByLabel("Your question").press("Escape");
  await expect(launcher).toBeFocused();
});

test("a Next.js page can mount and unmount across client-side navigation", async ({ page }) => {
  await watchListeners(page);
  await standInFrames(page);
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  const before = await listeners(page);
  await embed(page, bot.public_key);
  for (let round = 0; round < 3; round++) {
    await page.getByRole("link", { name: /forgot/i }).click(); // client-side navigation
    await expect(page).toHaveURL(/\/forgot-password/);
    await embed(page, bot.public_key);
    await expect(frames(page)).toHaveCount(1);
    await destroy(page, bot.public_key);
    await expect(frames(page)).toHaveCount(0);
    await page.getByRole("link", { name: "Back to sign in" }).click();
    await expect(page).toHaveURL(/\/login/);
    await embed(page, bot.public_key);
    await expect(frames(page)).toHaveCount(1);
  }
  await destroy(page, bot.public_key);
  await expect(frames(page)).toHaveCount(0);
  expect(await listeners(page)).toBe(before);
});
