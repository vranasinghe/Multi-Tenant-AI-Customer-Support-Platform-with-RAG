import { expect, test } from "@playwright/test";

import { openHydrated, signUpVerified } from "./helpers";

/**
 * Upload → background indexing (real Celery worker, S3-compatible storage, pgvector) → retrieval →
 * delete, driven through the dashboard. Requires the Docker stack including the worker.
 */

const POLICY = [
  "# Store policy",
  "",
  "## Returns",
  "Unworn items may be returned within thirty days of delivery for a full refund.",
  "",
  "## Shipping",
  "Standard shipping takes four to six business days. Express shipping takes two business days.",
  "",
].join("\n");

test("upload a document, see it indexed, search it, then delete it", async ({ page, request }) => {
  const orgPath = await signUpVerified(page, request);

  // a chatbot to attach knowledge to
  await openHydrated(page, `${orgPath}/chatbots/new`);
  await page.getByLabel("Name").fill("Knowledge Bot");
  for (let step = 0; step < 4; step += 1)
    await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Create chatbot" }).click();
  await expect(page).toHaveURL(/\/chatbots\/[0-9a-f-]{36}$/);

  // empty state, then upload
  await openHydrated(page, `${orgPath}/knowledge`);
  await expect(page.getByRole("heading", { name: "No documents yet" })).toBeVisible();

  // client-side validation: unsupported type is refused before any request
  await page.getByLabel("Choose files to upload").setInputFiles({
    name: "malware.exe",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("MZ not really"),
  });
  await expect(page.getByText(/Unsupported type/)).toBeVisible();

  await page.getByLabel("Choose files to upload").setInputFiles({
    name: "policy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(POLICY),
  });
  await expect(page.getByText(/Uploaded\. Processing continues/)).toBeVisible();

  // the worker indexes it; the row flips to Ready without a manual refresh
  const row = page.getByRole("row", { name: /policy\.txt/ });
  await expect(row).toBeVisible();
  await expect(row.getByText("Ready")).toBeVisible({ timeout: 60_000 });
  await expect(row.getByText(/\d+ passages/)).toBeVisible();

  // re-uploading identical bytes is refused by the server
  await page.getByLabel("Choose files to upload").setInputFiles({
    name: "policy-copy.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(POLICY),
  });
  await expect(
    page.getByText("This exact file was already uploaded to this chatbot."),
  ).toBeVisible();

  // passages preview shows the heading path
  await row.getByRole("button", { name: /Passages/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/Store policy › Returns/)).toBeVisible();
  await page.keyboard.press("Escape");

  // retrieval returns the right passage
  await page.getByRole("tab", { name: "Test retrieval" }).click();
  await page.getByLabel("Question").fill("How many days do I have to return an item?");
  await page.getByRole("button", { name: "Search" }).click();
  const results = page.getByRole("region", { name: "Search results" });
  await expect(results.getByText(/within thirty days of delivery/)).toBeVisible();

  // delete removes the document and its vectors
  await page.getByRole("tab", { name: "Documents" }).click();
  await page.getByRole("button", { name: "Delete policy.txt" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Delete document" }).click();
  await expect(page.getByText("Document deleted")).toBeVisible();
  await expect(page.getByRole("heading", { name: "No documents yet" })).toBeVisible();

  await page.getByRole("tab", { name: "Test retrieval" }).click();
  await page.getByLabel("Question").fill("How many days do I have to return an item?");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("heading", { name: "No relevant passages" })).toBeVisible();
});

test("private website addresses are refused", async ({ page, request }) => {
  const orgPath = await signUpVerified(page, request);
  await openHydrated(page, `${orgPath}/chatbots/new`);
  await page.getByLabel("Name").fill("Site Bot");
  for (let step = 0; step < 4; step += 1)
    await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Create chatbot" }).click();
  await expect(page).toHaveURL(/\/chatbots\/[0-9a-f-]{36}$/);

  await openHydrated(page, `${orgPath}/knowledge`);
  await page.getByRole("tab", { name: "Websites" }).click();
  await page.getByLabel("Starting address").fill("http://169.254.169.254/latest/meta-data/");
  await page.getByLabel(/I own this website/).check();
  await page.getByRole("button", { name: "Add website" }).click();

  await expect(page.getByRole("alert").first()).toContainText(/Only public websites/);
  await expect(page.getByRole("heading", { name: "No websites yet" })).toBeVisible();
});
