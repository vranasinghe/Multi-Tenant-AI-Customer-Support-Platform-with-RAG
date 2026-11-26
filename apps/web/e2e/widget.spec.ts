import { createServer, type Server } from "node:http";
import { expect, test } from "@playwright/test";
import { API_URL, WEB_ORIGIN, signUpVerified } from "./helpers";

let server: Server;
test.beforeAll(async () => {
  server = createServer((_req, res) => {
    res.setHeader("Content-Type", "text/html");
    res.end(
      "<!doctype html><html><head><title>Plain HTML fixture</title></head><body><h1>Customer website</h1></body></html>",
    );
  });
  await new Promise<void>((resolve) => server.listen(3101, "127.0.0.1", resolve));
});
test.afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

test("widget streams on HTML and Next.js, isolates instances, resumes and renders hostile text safely", async ({
  page,
  request,
}) => {
  const org = await signUpVerified(page, request);
  const headers = { "X-Requested-With": "platform", Origin: WEB_ORIGIN };
  const bots: { id: string; public_key: string }[] = [];
  for (let i = 0; i < 2; i++) {
    const created = await page.request.post(`${API_URL}/api/v1${org}/chatbots`, {
      headers,
      data: {
        name: `Widget ${i}`,
        status: "active",
        welcome_message: '<img src=x onerror="window.pwned=1"> Welcome!',
        widget_settings: { position: i ? "bottom-left" : "bottom-right", primary_color: "#123456" },
      },
    });
    expect(created.status()).toBe(201);
    const bot = (await created.json()) as { id: string; public_key: string };
    bots.push(bot);
    const base = `${API_URL}/api/v1${org}/chatbots/${bot.id}`;
    for (const origin of ["http://localhost:3101", WEB_ORIGIN]) {
      expect(
        (await page.request.post(base + "/domains", { headers, data: { origin } })).status(),
      ).toBe(201);
      const conf = (await (
        await page.request.get(base + "/widget-config", { headers })
      ).json()) as { domains: { id: string; origin: string }[] };
      const d = conf.domains.find((d) => d.origin === origin)!;
      expect(
        (await page.request.post(base + `/domains/${d.id}/verify`, { headers })).status(),
      ).toBe(200);
    }
  }
  const bot = bots[0]!;
  const base = `${API_URL}/api/v1${org}/chatbots/${bot.id}`;
  const uploaded = await page.request.post(base + "/documents?filename=returns.txt", {
    headers: { ...headers, "Content-Type": "text/plain" },
    data: Buffer.from(
      "Returns are allowed within thirty days of delivery. Items must be unused in original packaging.",
    ),
  });
  expect(uploaded.status()).toBe(201);
  const doc = (await uploaded.json()) as { id: string };
  await expect
    .poll(
      async () =>
        (
          (await (await page.request.get(base + `/documents/${doc.id}`)).json()) as {
            status: string;
          }
        ).status,
      { timeout: 60000 },
    )
    .toBe("ready");
  async function embed(key: string) {
    await page.evaluate(
      ({ api, key }) => {
        const s = document.createElement("script");
        s.src = api + "/widget/v1/loader.js";
        s.dataset.botKey = key;
        document.body.append(s);
      },
      { api: API_URL, key },
    );
  }
  await page.goto("http://localhost:3101");
  await embed(bot.public_key);
  await embed(bots[1]!.public_key);
  const first = page.frameLocator(`iframe[src*="/widget/frame/${bot.public_key}"]`);
  const second = page.frameLocator(`iframe[src*="/widget/frame/${bots[1]!.public_key}"]`);
  await first.getByRole("button", { name: "Open support chat" }).click();
  await expect(first.getByRole("log")).toContainText("<img src=x");
  expect(
    await first
      .locator("body")
      .evaluate(() => Boolean((window as unknown as { pwned?: number }).pwned)),
  ).toBe(false);
  await first.getByLabel("Your question").fill("Returns policy?");
  await first.getByRole("button", { name: "Send", exact: true }).click();
  await expect(first.getByRole("log")).toContainText("Demo response");
  await expect(first.getByRole("log")).toContainText("returns.txt");
  await first.getByRole("button", { name: "Close support chat" }).click();
  await second.getByRole("button", { name: "Open support chat" }).click();
  await expect(second.getByRole("log")).not.toContainText("Returns policy?");
  await second.getByRole("button", { name: "Close support chat" }).click();
  await page.reload();
  await embed(bot.public_key);
  await first.getByRole("button", { name: "Open support chat" }).click();
  await expect(first.getByRole("log")).toContainText("Demo response");
  await first.getByLabel("Your question").press("Escape");
  await expect(first.getByRole("button", { name: "Open support chat" })).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await first.getByRole("button", { name: "Open support chat" }).click();
  const rect = await page.locator("iframe").first().boundingBox();
  expect(rect!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/widget-mobile.png", fullPage: true });
  await page.goto("/login");
  await embed(bot.public_key);
  await first.getByRole("button", { name: "Open support chat" }).click();
  await expect(first.getByRole("log")).not.toContainText("Returns policy?");
  await expect(first.getByLabel("Your question")).toBeVisible();
  await page.goto(`${org}/chatbots/${bot.id}`);
  await page.getByRole("tab", { name: "Install", exact: true }).click();
  await expect(page.getByLabel("Installation script")).toHaveValue(new RegExp(bot.public_key));
  // Playwright's headless Chromium (used in CI) refuses clipboard writes unless granted.
  await page.context().grantPermissions(["clipboard-write"], { origin: WEB_ORIGIN });
  await page.getByRole("button", { name: "Copy installation script" }).click();
  await expect(page.getByRole("button", { name: "Copied", exact: true })).toBeVisible();
  await page.locator('iframe[title="Live widget preview"]').scrollIntoViewIfNeeded();
  const preview = page.frameLocator('iframe[title="Live widget preview"]');
  await preview.getByRole("button", { name: "Open support chat" }).click();
  await expect(preview.getByLabel("Your question")).toBeVisible();
  await page.screenshot({ path: "test-results/widget-dashboard.png", fullPage: true });
});
