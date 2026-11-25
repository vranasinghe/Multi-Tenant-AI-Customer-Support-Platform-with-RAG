// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { AuthState } from "@/lib/auth/auth-context";

const mocks = vi.hoisted(() => ({
  lookupInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  signOut: vi.fn(),
  auth: { status: "anonymous" } as AuthState,
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return {
    ApiError: actual.ApiError,
    api: { lookupInvitation: mocks.lookupInvitation, acceptInvitation: mocks.acceptInvitation },
  };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
}));
vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({
    state: mocks.auth,
    refresh: mocks.refresh,
    signOut: mocks.signOut,
    setSession: vi.fn(),
  }),
}));

import { InviteAcceptance } from "./invite-acceptance";

const TOKEN = "i".repeat(43);
const PREVIEW = {
  org_name: "Acme",
  inviter_name: "Olivia",
  role: "agent" as const,
  email_hint: "d***@acme.com",
};
const signedIn = (email: string, verified = true): AuthState => ({
  status: "authenticated",
  user: { id: "u1", email, name: "Dana", email_verified: verified, locale: "en" },
  orgs: [],
});

beforeEach(() => {
  Object.values(mocks).forEach((m) => typeof m === "function" && "mockReset" in m && m.mockReset());
  mocks.auth = { status: "anonymous" };
  mocks.lookupInvitation.mockResolvedValue(PREVIEW);
  mocks.refresh.mockResolvedValue(signedIn("dana@acme.com"));
  window.localStorage.clear();
});

describe("InviteAcceptance", () => {
  it("explains a missing token", () => {
    render(<InviteAcceptance token={null} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/missing or incomplete/i);
    expect(mocks.lookupInvitation).not.toHaveBeenCalled();
  });

  it("shows who invited you, to what, and as which role, without the full email", async () => {
    render(<InviteAcceptance token={TOKEN} />);

    expect(await screen.findByText(/Olivia invited you to join/i)).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(/d\*\*\*@acme\.com/)).toBeInTheDocument();
    expect(screen.getByText(/agent/i)).toBeInTheDocument();
  });

  it("sends anonymous visitors to sign in or sign up and brings them back to this invitation", async () => {
    render(<InviteAcceptance token={TOKEN} />);
    await screen.findByText(/Olivia invited you/i);

    const back = encodeURIComponent(`/invite?token=${TOKEN}`);
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute(
      "href",
      `/login?next=${back}`,
    );
    expect(screen.getByRole("link", { name: /create an account/i })).toHaveAttribute(
      "href",
      `/signup?next=${back}`,
    );
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  });

  it("accepts, refreshes memberships, remembers the org and opens it", async () => {
    mocks.auth = signedIn("dana@acme.com");
    mocks.acceptInvitation.mockResolvedValue({ id: "o9", name: "Acme", role: "agent" });
    render(<InviteAcceptance token={TOKEN} />);
    await screen.findByText(/Olivia invited you/i);

    await userEvent.click(screen.getByRole("button", { name: /accept invitation/i }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/orgs/o9"));
    expect(mocks.acceptInvitation).toHaveBeenCalledWith(TOKEN);
    expect(mocks.refresh).toHaveBeenCalled();
    expect(window.localStorage.getItem("acs.activeOrg")).toBe("o9");
  });

  it("tells a signed-in user with the wrong account which account is needed, and offers sign-out", async () => {
    mocks.auth = signedIn("someone.else@gmail.com");
    mocks.acceptInvitation.mockRejectedValue(
      new ApiError({ status: 403, code: "forbidden", message: "x" }),
    );
    render(<InviteAcceptance token={TOKEN} />);
    await screen.findByText(/Olivia invited you/i);

    await userEvent.click(screen.getByRole("button", { name: /accept invitation/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/someone\.else@gmail\.com/);
    expect(alert).toHaveTextContent(/d\*\*\*@acme\.com/);
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(mocks.signOut).toHaveBeenCalled();
  });

  it("asks unverified users to verify first", async () => {
    mocks.auth = signedIn("dana@acme.com", false);
    mocks.acceptInvitation.mockRejectedValue(
      new ApiError({ status: 403, code: "email_not_verified", message: "x" }),
    );
    render(<InviteAcceptance token={TOKEN} />);
    await screen.findByText(/Olivia invited you/i);

    await userEvent.click(screen.getByRole("button", { name: /accept invitation/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/verify your email/i);
  });

  it("reports a used or expired invitation and hides the accept button", async () => {
    mocks.auth = signedIn("dana@acme.com");
    mocks.lookupInvitation.mockRejectedValue(
      new ApiError({ status: 400, code: "invalid_token", message: "x" }),
    );
    render(<InviteAcceptance token={TOKEN} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or has expired/i);
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  });

  it("does not double-submit", async () => {
    mocks.auth = signedIn("dana@acme.com");
    mocks.acceptInvitation.mockReturnValue(new Promise(() => undefined));
    render(<InviteAcceptance token={TOKEN} />);
    await screen.findByText(/Olivia invited you/i);

    await userEvent.click(screen.getByRole("button", { name: /accept invitation/i }));
    const busy = await screen.findByRole("button", { name: /joining/i });

    expect(busy).toBeDisabled();
    expect(mocks.acceptInvitation).toHaveBeenCalledTimes(1);
  });
});
