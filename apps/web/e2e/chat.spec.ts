import { expect, test } from "@playwright/test";
import { API_URL, WEB_ORIGIN, openHydrated, signUpVerified } from "./helpers";

// Run with LLM_PROVIDER=demo. No paid model calls; generation quality is not evaluated here.
test("indexed knowledge streams in the playground, persists, and accepts feedback", async ({
  page,
  request,
}) => {
  const orgPath = await signUpVerified(page, request);
  const headers = { "X-Requested-With": "platform", Origin: WEB_ORIGIN };
  const created = await page.request.post(`${API_URL}/api/v1${orgPath}/chatbots`, {
    headers,
    data: { name: "Conversation Demo" },
  });
  expect(created.status()).toBe(201);
  const bot = (await created.json()) as { id: string };
  const base = `${API_URL}/api/v1${orgPath}/chatbots/${bot.id}`;
  const upload = await page.request.post(`${base}/documents?filename=returns.txt`, {
    headers: { ...headers, "Content-Type": "text/plain" },
    data: Buffer.from(
      "Returns are allowed within thirty days of delivery. Returned items must be unused and in original packaging.",
    ),
  });
  expect(upload.status()).toBe(201);
  const doc = (await upload.json()) as { id: string };
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`${base}/documents/${doc.id}`);
        return ((await response.json()) as { status: string }).status;
      },
      { timeout: 60000 },
    )
    .toBe("ready");

  await openHydrated(page, `${orgPath}/chatbots/${bot.id}`);
  await page.getByRole("tab", { name: "Test chat" }).click();
  await page.getByLabel("Customer question").fill("What is the returns policy?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText(/Demo response: this confirms/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Mark answer helpful" })).toBeVisible();
  await expect(page.getByRole("log")).toContainText("returns.txt");
  await page.getByRole("button", { name: "Mark answer helpful" }).click();
  await expect(page.getByRole("button", { name: "Mark answer helpful" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.screenshot({ path: "test-results/chat-desktop.png", fullPage: true });

  await page.reload();
  await page.getByRole("tab", { name: "Test chat" }).click();
  await expect(page.getByText(/Demo response: this confirms/)).toBeVisible();
  await page.getByRole("button", { name: "New conversation" }).click();
  await page.getByLabel("Customer question").fill("Explain astrophysics quasars galaxies?");
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText("Insufficient evidence")).toBeVisible();
  await expect(page.getByRole("log")).not.toContainText("Demo response");

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Customer question")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/chat-mobile.png", fullPage: true });
});
