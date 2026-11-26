import { createServer, type Server } from "node:http";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { API_URL, WEB_ORIGIN, openHydrated, signUpVerified } from "./helpers";

// AUD-06. Real widget and playground conversations, all content synthetic. Run with
// LLM_PROVIDER=demo. Set E2E_SHOT_DIR to keep screenshots.

const SITE = "http://localhost:3102";
const HEADERS = { "X-Requested-With": "platform", Origin: WEB_ORIGIN };
const SHOTS = process.env.E2E_SHOT_DIR ?? "test-results";

// Sign-ups are limited per IP, so the journeys share one account, each in its own organization.
let cookies: Awaited<ReturnType<BrowserContext["cookies"]>>;
test.beforeAll(async ({ browser, playwright }) => {
  const context = await browser.newContext({ baseURL: WEB_ORIGIN });
  const request = await playwright.request.newContext();
  await signUpVerified(await context.newPage(), request);
  cookies = await context.cookies();
  await request.dispose();
  await context.close();
});

async function freshOrg(page: Page, name: string): Promise<string> {
  await page.context().addCookies(cookies);
  const created = await page.request.post(`${API_URL}/api/v1/orgs`, {
    headers: HEADERS,
    data: { name },
  });
  expect(created.status()).toBe(201);
  return `/orgs/${((await created.json()) as { id: string }).id}`;
}

let server: Server;
test.beforeAll(async () => {
  server = createServer((_req, res) => {
    res.setHeader("Content-Type", "text/html");
    res.end("<!doctype html><title>Customer site</title><h1>Customer website</h1>");
  });
  await new Promise<void>((resolve) => server.listen(3102, "127.0.0.1", resolve));
});
test.afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
});

const shot = (page: Page, name: string) =>
  page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });

const noSidewaysScroll = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);

async function createBot(page: Page, org: string, name: string) {
  const response = await page.request.post(`${API_URL}/api/v1${org}/chatbots`, {
    headers: HEADERS,
    data: { name, status: "active" },
  });
  expect(response.status()).toBe(201);
  return (await response.json()) as { id: string; public_key: string };
}

/** A playground conversation through the same API the dashboard test chat uses. */
async function playground(page: Page, org: string, bot: string, question: string) {
  const created = await page.request.post(`${API_URL}/api/v1${org}/chatbots/${bot}/conversations`, {
    headers: HEADERS,
    data: {},
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  const sent = await page.request.post(`${API_URL}/api/v1${org}/conversations/${id}/messages`, {
    headers: HEADERS,
    data: { content: question },
  });
  expect(sent.status()).toBe(200);
  await sent.text();
  return id;
}

const inboxList = (page: Page) => page.getByRole("list", { name: "Conversations" });

test("a website visitor's conversation reaches the inbox with its sources and stays there", async ({
  page,
}) => {
  const org = await freshOrg(page, "Website Org");
  const bot = await createBot(page, org, "Website Helper");
  const base = `${API_URL}/api/v1${org}/chatbots/${bot.id}`;
  expect(
    (
      await page.request.post(`${base}/domains`, { headers: HEADERS, data: { origin: SITE } })
    ).status(),
  ).toBe(201);
  const config = (await (
    await page.request.get(`${base}/widget-config`, { headers: HEADERS })
  ).json()) as { domains: { id: string; origin: string }[] };
  const domain = config.domains.find((item) => item.origin === SITE)!;
  await page.request.post(`${base}/domains/${domain.id}/verify`, { headers: HEADERS });
  const uploaded = await page.request.post(`${base}/documents?filename=returns.txt`, {
    headers: { ...HEADERS, "Content-Type": "text/plain" },
    data: Buffer.from(
      "Returns are allowed within thirty days of delivery. Items must be unused in original packaging.",
    ),
  });
  expect(uploaded.status()).toBe(201);
  const document = (await uploaded.json()) as { id: string };
  await expect
    .poll(
      async () =>
        (
          (await (await page.request.get(`${base}/documents/${document.id}`)).json()) as {
            status: string;
          }
        ).status,
      { timeout: 60_000 },
    )
    .toBe("ready");

  const visitor = await page.context().browser()!.newPage();
  await visitor.goto(SITE);
  await visitor.evaluate(
    ({ api, key }) => {
      const script = window.document.createElement("script");
      script.src = `${api}/widget/v1/loader.js`;
      script.dataset.botKey = key;
      window.document.body.append(script);
    },
    { api: API_URL, key: bot.public_key },
  );
  const widget = visitor.frameLocator(`iframe[src*="/widget/frame/${bot.public_key}"]`);
  await widget.getByRole("button", { name: "Open support chat" }).click();
  await widget.getByLabel("Your question").fill("Are returns allowed within thirty days?");
  await widget.getByRole("button", { name: "Send", exact: true }).click();
  await expect(widget.getByRole("log")).toContainText("Demo response");
  await expect(widget.getByRole("log")).toContainText("returns.txt");
  await visitor.close();

  await openHydrated(page, `${org}/conversations`);
  const row = inboxList(page).getByRole("link", { name: /thirty days/ });
  await expect(row).toContainText("Website Helper");
  await expect(row).toContainText("widget");
  await shot(page, "inbox-list-desktop");
  await row.click();

  const history = page.getByRole("list", { name: "Message history" });
  await expect(history).toContainText("Are returns allowed within thirty days?");
  await expect(history).toContainText("Demo response");
  await expect(history.getByRole("list", { name: "Sources" })).toContainText("returns.txt");
  await expect(history.locator("time").first()).toHaveAttribute("datetime", /^\d{4}-\d{2}-\d{2}T/);
  await shot(page, "transcript-desktop");

  await page.reload();
  await expect(history).toContainText("Are returns allowed within thirty days?");
  await expect(history.getByRole("list", { name: "Sources" })).toContainText("returns.txt");
});

test("playground conversations are listed by channel and filtered by chatbot", async ({ page }) => {
  const org = await freshOrg(page, "Playground Org");
  const first = await createBot(page, org, "Orders Bot");
  const second = await createBot(page, org, "Billing Bot");
  await playground(page, org, first.id, "Where is my parcel?");
  await playground(page, org, second.id, "Why was my card charged twice?");

  await openHydrated(page, `${org}/conversations`);
  await expect(inboxList(page).getByRole("link")).toHaveCount(2);
  await expect(inboxList(page).getByRole("link", { name: /parcel/ })).toContainText("playground");

  await page.getByRole("combobox", { name: "Chatbot" }).selectOption({ label: "Billing Bot" });
  await expect(inboxList(page).getByRole("link")).toHaveCount(1);
  await expect(inboxList(page)).toContainText("charged twice");
  await expect(inboxList(page)).not.toContainText("parcel");

  await page.getByRole("combobox", { name: "Channel" }).selectOption("widget");
  await expect(page.getByRole("heading", { name: "No matching conversations" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(inboxList(page).getByRole("link")).toHaveCount(2);
});

test("the inbox works from the keyboard and on a 390px screen", async ({ page }) => {
  const org = await freshOrg(page, "Mobile Org");
  const bot = await createBot(page, org, "Mobile Bot");
  await playground(page, org, bot.id, `Unbroken ${"reference".repeat(20)} question`);
  await playground(page, org, bot.id, "Short question");

  await page.setViewportSize({ width: 390, height: 844 });
  await openHydrated(page, `${org}/conversations`);
  expect(await noSidewaysScroll(page)).toBe(true);
  await shot(page, "inbox-list-390px");

  // Tab from the search box until a conversation link has focus, then open it.
  await page.getByRole("searchbox", { name: "Search conversations" }).focus();
  const target = inboxList(page).getByRole("link", { name: /Short question/ });
  for (let i = 0; i < 20; i++) {
    if (await target.evaluate((node) => node === window.document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
  const outline = await target.evaluate((node) => getComputedStyle(node).boxShadow);
  expect(outline).not.toBe("none");
  await page.keyboard.press("Enter");

  await expect(page.getByRole("list", { name: "Message history" })).toContainText("Short question");
  expect(await noSidewaysScroll(page)).toBe(true);
  await shot(page, "transcript-390px");

  const back = page.getByRole("link", { name: "All conversations" });
  await back.focus();
  await page.keyboard.press("Enter");
  await expect(inboxList(page)).toContainText("Short question");

  await inboxList(page)
    .getByRole("link", { name: /Unbroken/ })
    .click();
  await expect(page.getByRole("list", { name: "Message history" })).toBeVisible();
  expect(await noSidewaysScroll(page)).toBe(true);
});

test("one organization's conversations never appear in another's inbox", async ({
  page,
  request,
  browser,
}) => {
  const orgA = await freshOrg(page, "First Org");
  const botA = await createBot(page, orgA, "Alpha Bot");
  const secretA = await playground(page, orgA, botA.id, "Alpha confidential question");
  const orgB = await freshOrg(page, "Second Org");
  const orgBId = orgB.split("/").pop()!;
  const botB = await createBot(page, orgB, "Beta Bot");
  await playground(page, orgB, botB.id, "Beta ordinary question");

  await openHydrated(page, `${orgA}/conversations`);
  await expect(inboxList(page)).toContainText("Alpha confidential question");

  // Hold the second organization's answer back: nothing of the first may stay meanwhile.
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(`${API_URL}/api/v1${orgB}/conversations?*`, async (route) => {
    await held;
    await route.continue();
  });
  await page.getByRole("combobox", { name: "Organization" }).selectOption(orgBId);
  await expect(page).toHaveURL(new RegExp(`${orgBId}$`));
  await page.getByRole("link", { name: "Conversations", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Loading conversations" })).toBeVisible();
  await expect(page.getByText("Alpha confidential question")).toHaveCount(0);
  await expect(page.getByRole("option", { name: "Alpha Bot" })).toHaveCount(0);
  release();
  await expect(inboxList(page)).toContainText("Beta ordinary question");
  await expect(page.getByText("Alpha confidential question")).toHaveCount(0);

  // The first organization's identifier inside the second one's scope.
  for (const path of [`${secretA}`, `${secretA}/messages`]) {
    const crossed = await page.request.get(`${API_URL}/api/v1${orgB}/conversations/${path}`);
    expect(crossed.status()).toBe(404);
    expect(await crossed.text()).not.toContain("Alpha confidential");
  }
  await openHydrated(page, `${orgB}/conversations/${secretA}`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("don't have access");
  await expect(page.getByText("Alpha confidential question")).toHaveCount(0);

  // A different, signed-in person who is a member of neither.
  const other = await browser.newPage();
  await signUpVerified(other, request);
  const foreign = await other.request.get(`${API_URL}/api/v1${orgA}/conversations`);
  expect(foreign.status()).toBe(404);
  await openHydrated(other, `${orgA}/conversations`);
  await expect(other.getByRole("heading", { name: "Organization not found" })).toBeVisible();
  await expect(other.getByText("Alpha confidential question")).toHaveCount(0);
  await other.close();

  // Signing out leaves nothing behind, including on the way back.
  await openHydrated(page, `${orgA}/conversations`);
  await expect(inboxList(page)).toContainText("Alpha confidential question");
  await page
    .getByRole("button", { name: /sign out|log out/i })
    .first()
    .click();
  await expect(page).toHaveURL(/\/login/);
  await page.goBack();
  await expect(page.getByText("Alpha confidential question")).toHaveCount(0);
});
