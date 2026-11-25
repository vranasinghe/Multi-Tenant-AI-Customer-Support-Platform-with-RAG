import { expect, test } from "@playwright/test";

import {
  API_URL,
  WEB_ORIGIN,
  generatedPassword,
  openHydrated,
  uniqueEmail,
  verificationToken,
} from "./helpers";

/**
 * Sign up → verify email (token read from Mailpit) → create a chatbot with the wizard → see it
 * in the list after a reload. Runs against the real API and database.
 */

test("a new user creates a chatbot with the wizard", async ({ page, request }) => {
  const email = uniqueEmail();
  const password = generatedPassword();

  // --- sign up -------------------------------------------------------------------------
  await openHydrated(page, "/signup");
  await page.getByLabel("Your name").fill("E2E Owner");
  await page.getByLabel("Organization name").fill("E2E Org");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/orgs\/[0-9a-f-]{36}$/);
  const orgPath = new URL(page.url()).pathname;

  // --- verify the email (creating chatbots requires it) ---------------------------------
  const token = await verificationToken(request, email);
  const verified = await request.post(`${API_URL}/api/v1/auth/verify-email`, {
    data: { token },
    headers: { "X-Requested-With": "platform", Origin: WEB_ORIGIN },
  });
  expect(verified.status()).toBe(200);

  // --- empty state ------------------------------------------------------------------------
  await openHydrated(page, `${orgPath}/chatbots`);
  await expect(page.getByRole("heading", { name: "No chatbots yet" })).toBeVisible();
  await page.getByRole("link", { name: "Create chatbot" }).click();
  await expect(page.getByRole("heading", { name: "Create a chatbot" })).toBeVisible();

  // --- step 1: basics (validation first) ---------------------------------------------------
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Enter a name.")).toBeVisible();
  await expect(page.getByLabel("Name")).toBeFocused();
  await page.getByLabel("Name").fill("E2E Support Bot");
  await page.getByLabel("Description").fill("Created by the end-to-end test");
  await page.getByRole("button", { name: "Continue" }).click();

  // --- step 2: behavior --------------------------------------------------------------------
  await expect(page.getByRole("heading", { name: "Behavior" })).toBeVisible();
  await page.getByLabel("System instructions").fill("Answer questions about E2E orders.");
  await page.getByText("Friendly", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();

  // --- step 3: appearance ------------------------------------------------------------------
  await expect(page.getByRole("heading", { name: "Appearance" })).toBeVisible();
  await page.getByLabel("Brand color", { exact: true }).fill("#0F766E");
  await page.getByRole("button", { name: "Continue" }).click();

  // --- step 4: model -----------------------------------------------------------------------
  await expect(page.getByRole("heading", { name: "Model" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  // --- step 5: review & create -------------------------------------------------------------
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByRole("definition").filter({ hasText: "E2E Support Bot" })).toBeVisible();
  await page.getByRole("button", { name: "Create chatbot" }).click();

  await expect(page).toHaveURL(/\/chatbots\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: "E2E Support Bot" })).toBeVisible();
  await expect(page.getByText("Chatbot created")).toBeVisible();

  // --- persisted on the server: visible in the list after a full reload ---------------------
  await openHydrated(page, `${orgPath}/chatbots`);
  const row = page.getByRole("listitem").filter({ hasText: "E2E Support Bot" });
  await expect(row).toBeVisible();
  await expect(row.getByText("Draft")).toBeVisible();
  await expect(page.getByText("1 of 25 chatbots used")).toBeVisible();
});
