import { expect, test } from "@playwright/test";

import { API_URL, WEB_ORIGIN, openHydrated, signUpVerified } from "./helpers";

test("conversation inbox and analytics dashboard show stored events", async ({ page, request }) => {
  const orgPath = await signUpVerified(page, request);
  const headers = { "X-Requested-With": "platform", Origin: WEB_ORIGIN };
  const created = await page.request.post(`${API_URL}/api/v1${orgPath}/chatbots`, {
    headers,
    data: { name: "Inbox Bot" },
  });
  expect(created.status()).toBe(201);
  const bot = (await created.json()) as { id: string };
  const conv = await page.request.post(
    `${API_URL}/api/v1${orgPath}/chatbots/${bot.id}/conversations`,
    { headers, data: {} },
  );
  expect(conv.status()).toBe(201);
  const conversation = (await conv.json()) as { id: string };
  const sent = await page.request.post(
    `${API_URL}/api/v1${orgPath}/conversations/${conversation.id}/messages`,
    { headers, data: { content: "Do you ship to Canada?" } },
  );
  expect(sent.status()).toBe(200);

  await openHydrated(page, `${orgPath}/conversations`);
  await expect(page.getByRole("search", { name: "Conversation filters" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Conversations" })).toContainText("Canada");
  await page.getByRole("link", { name: /Canada/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Canada");
  await expect(page.getByRole("list", { name: "Message history" })).toBeVisible();
  await page.getByRole("button", { name: "Mark resolved" }).click();
  await expect(page.getByRole("status", { name: "Resolved" })).toBeVisible();

  await openHydrated(page, `${orgPath}/analytics`);
  await expect(page.getByRole("heading", { name: "Analytics", exact: true })).toBeVisible();
  await expect(page.getByText(/playground tests are excluded/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Knowledge gaps" })).toBeVisible();
});
