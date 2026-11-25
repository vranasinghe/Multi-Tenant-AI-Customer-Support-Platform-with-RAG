import { expect } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

/** Shared end-to-end helpers. Everything runs against the real API, worker, storage and database. */

export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? "http://127.0.0.1:8025";
export const WEB_ORIGIN = new URL(process.env.E2E_BASE_URL ?? "http://localhost:3000").origin;

export function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/** Throwaway password generated per run; never a real credential. */
export function generatedPassword(): string {
  return `e2e-${crypto.randomUUID()}`;
}

export async function verificationToken(
  request: APIRequestContext,
  email: string,
): Promise<string> {
  let token: string | undefined;
  await expect
    .poll(
      async () => {
        const search = await request.get(
          `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:${email}`)}`,
        );
        const { messages } = (await search.json()) as { messages: { ID: string }[] };
        if (!messages?.length) return null;
        const message = await request.get(`${MAILPIT_URL}/api/v1/message/${messages[0]!.ID}`);
        const { Text } = (await message.json()) as { Text: string };
        token = /verify-email\?token=([A-Za-z0-9_-]+)/.exec(Text)?.[1];
        return token ?? null;
      },
      { message: "verification email should arrive in Mailpit", timeout: 20_000 },
    )
    .not.toBeNull();
  return token!;
}

/** Wait until React has hydrated, so a click can't fall back to a native form submit. */
export async function openHydrated(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

/** Sign up through the UI and verify the email through the API. Returns the org's URL path. */
export async function signUpVerified(page: Page, request: APIRequestContext): Promise<string> {
  const email = uniqueEmail();
  await openHydrated(page, "/signup");
  await page.getByLabel("Your name").fill("E2E Owner");
  await page.getByLabel("Organization name").fill("E2E Org");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(generatedPassword());
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/orgs\/[0-9a-f-]{36}$/);
  const orgPath = new URL(page.url()).pathname;

  const token = await verificationToken(request, email);
  const verified = await request.post(`${API_URL}/api/v1/auth/verify-email`, {
    data: { token },
    headers: { "X-Requested-With": "platform", Origin: WEB_ORIGIN },
  });
  expect(verified.status()).toBe(200);
  return orgPath;
}
