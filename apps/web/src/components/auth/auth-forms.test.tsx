// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { MeResponse } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  signup: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  replace: vi.fn(),
  setSession: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return {
    ApiError: actual.ApiError,
    api: {
      login: mocks.login,
      signup: mocks.signup,
      forgotPassword: mocks.forgotPassword,
      resetPassword: mocks.resetPassword,
    },
  };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
}));
vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({
    state: { status: "anonymous" },
    setSession: mocks.setSession,
    refresh: mocks.refresh,
    signOut: vi.fn(),
  }),
}));

import { ForgotPasswordForm } from "./forgot-password-form";
import { LoginForm } from "./login-form";
import { ResetPasswordForm } from "./reset-password-form";
import { SignupForm } from "./signup-form";

const ME: MeResponse = {
  user: { id: "u1", email: "dana@acme.com", name: "Dana", email_verified: true, locale: "en" },
  orgs: [{ id: "o1", name: "Acme", role: "owner" }],
};
const problem = (
  status: number,
  code: string,
  message = "msg",
  extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {},
) => new ApiError({ status, code, message, ...extra });

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
});

describe("LoginForm", () => {
  async function fill(email = "dana@acme.com", password = "hunter2 hunter2") {
    await userEvent.type(screen.getByLabelText(/email/i), email);
    await userEvent.type(screen.getByLabelText(/^password/i), password);
  }

  it("validates before calling the API and marks the invalid fields", async () => {
    render(<LoginForm />);

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText(/email/i)).toHaveFocus();
    expect(mocks.login).not.toHaveBeenCalled();
  });

  it("signs in, adopts the session and goes to the dashboard by default", async () => {
    mocks.login.mockResolvedValue(ME);
    render(<LoginForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/dashboard"));
    expect(mocks.login).toHaveBeenCalledWith({
      email: "dana@acme.com",
      password: "hunter2 hunter2",
    });
    expect(mocks.setSession).toHaveBeenCalledWith(ME);
  });

  it("returns to a safe ?next= destination", async () => {
    mocks.login.mockResolvedValue(ME);
    render(<LoginForm next="/orgs/o1/members" />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/orgs/o1/members"));
  });

  it("refuses an open redirect in ?next=", async () => {
    mocks.login.mockResolvedValue(ME);
    render(<LoginForm next="https://evil.example/steal" />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("shows one non-revealing message for bad credentials, keeps the email and clears the password", async () => {
    mocks.login.mockRejectedValue(problem(401, "invalid_credentials"));
    render(<LoginForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect.");
    expect(screen.getByLabelText(/email/i)).toHaveValue("dana@acme.com");
    expect(screen.getByLabelText(/^password/i)).toHaveValue("");
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("explains rate limiting with the wait time", async () => {
    mocks.login.mockRejectedValue(problem(429, "rate_limited", "x", { retryAfterSeconds: 600 }));
    render(<LoginForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many attempts.*10 minutes/i);
  });

  it("shows a network failure without losing the form", async () => {
    mocks.login.mockRejectedValue(
      problem(0, "network_error", "Can't reach the server. Check your connection and try again."),
    );
    render(<LoginForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/can't reach the server/i);
    expect(screen.getByLabelText(/email/i)).toHaveValue("dana@acme.com");
  });

  it("disables the button while signing in so it can't be double-submitted", async () => {
    let resolve!: (me: MeResponse) => void;
    mocks.login.mockReturnValue(new Promise<MeResponse>((r) => (resolve = r)));
    render(<LoginForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

    const pending = await screen.findByRole("button", { name: /signing in/i });
    expect(pending).toBeDisabled();
    resolve(ME);
    await waitFor(() => expect(mocks.replace).toHaveBeenCalled());
    expect(mocks.login).toHaveBeenCalledTimes(1);
  });

  it("uses the right autocomplete hints and masks the password", () => {
    render(<LoginForm />);

    expect(screen.getByLabelText(/email/i)).toHaveAttribute("autocomplete", "username");
    expect(screen.getByLabelText(/^password/i)).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText(/^password/i)).toHaveAttribute("type", "password");
    expect(screen.getByRole("link", { name: /forgot password/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });
});

describe("SignupForm", () => {
  async function fill(
    overrides: Partial<Record<"name" | "org" | "email" | "password", string>> = {},
  ) {
    await userEvent.type(screen.getByLabelText(/your name/i), overrides.name ?? "Dana Lee");
    await userEvent.type(screen.getByLabelText(/organization name/i), overrides.org ?? "Acme");
    await userEvent.type(screen.getByLabelText(/email/i), overrides.email ?? "dana@acme.com");
    await userEvent.type(
      screen.getByLabelText(/^password/i),
      overrides.password ?? "correct horse battery staple",
    );
  }

  it("enforces the password policy client-side without calling the API", async () => {
    render(<SignupForm />);
    await fill({ password: "short" });

    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("Use at least 10 characters.")).toBeInTheDocument();
    expect(mocks.signup).not.toHaveBeenCalled();
  });

  it("creates the account and, when a session starts, continues to the dashboard", async () => {
    mocks.signup.mockResolvedValue({ user: ME.user, org: ME.orgs[0] });
    mocks.refresh.mockResolvedValue({ status: "authenticated", user: ME.user, orgs: ME.orgs });
    render(<SignupForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/dashboard"));
    expect(mocks.signup).toHaveBeenCalledWith({
      email: "dana@acme.com",
      password: "correct horse battery staple",
      name: "Dana Lee",
      org_name: "Acme",
    });
  });

  it("never reveals whether the email was already registered", async () => {
    mocks.signup.mockResolvedValue({ user: ME.user, org: ME.orgs[0] });
    mocks.refresh.mockResolvedValue({ status: "anonymous" }); // API issued no session
    render(<SignupForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/check your email/i);
    expect(screen.getByRole("status")).not.toHaveTextContent(
      /already (registered|exists|in use)|taken/i,
    );
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("maps server-side field errors onto the field", async () => {
    mocks.signup.mockRejectedValue(
      problem(422, "validation_error", "bad", {
        fieldErrors: { password: "That password is too common." },
      }),
    );
    render(<SignupForm />);
    await fill();

    await userEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText("That password is too common.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^password/i)).toHaveAttribute("aria-invalid", "true");
  });

  it("uses new-password autocomplete so password managers offer to save it", () => {
    render(<SignupForm />);

    expect(screen.getByLabelText(/^password/i)).toHaveAttribute("autocomplete", "new-password");
  });
});

describe("ForgotPasswordForm", () => {
  it("always gives the same confirmation, whether or not the account exists", async () => {
    mocks.forgotPassword.mockResolvedValue({ status: "accepted" });
    render(<ForgotPasswordForm />);

    await userEvent.type(screen.getByLabelText(/email/i), "nobody@example.com");
    await userEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      /if an account exists for nobody@example.com/i,
    );
  });

  it("shows the wait when rate limited", async () => {
    mocks.forgotPassword.mockRejectedValue(
      problem(429, "rate_limited", "x", { retryAfterSeconds: 3000 }),
    );
    render(<ForgotPasswordForm />);

    await userEvent.type(screen.getByLabelText(/email/i), "a@b.co");
    await userEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/50 minutes/i);
  });
});

describe("ResetPasswordForm", () => {
  it("requires matching passwords", async () => {
    render(<ResetPasswordForm token={"t".repeat(43)} />);

    await userEvent.type(screen.getByLabelText(/^new password/i), "a long enough passphrase");
    await userEvent.type(screen.getByLabelText(/confirm/i), "something else entirely");
    await userEvent.click(screen.getByRole("button", { name: /set new password/i }));

    expect(await screen.findByText("Passwords don't match.")).toBeInTheDocument();
    expect(mocks.resetPassword).not.toHaveBeenCalled();
  });

  it("submits the token from the link and points to sign-in on success", async () => {
    mocks.resetPassword.mockResolvedValue({ status: "password_reset" });
    const token = "t".repeat(43);
    render(<ResetPasswordForm token={token} />);

    await userEvent.type(screen.getByLabelText(/^new password/i), "a long enough passphrase");
    await userEvent.type(screen.getByLabelText(/confirm/i), "a long enough passphrase");
    await userEvent.click(screen.getByRole("button", { name: /set new password/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(/password updated/i);
    expect(mocks.resetPassword).toHaveBeenCalledWith(token, "a long enough passphrase");
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("tells the user a used or expired link is dead and offers a new one", async () => {
    mocks.resetPassword.mockRejectedValue(problem(400, "invalid_token"));
    render(<ResetPasswordForm token={"t".repeat(43)} />);

    await userEvent.type(screen.getByLabelText(/^new password/i), "a long enough passphrase");
    await userEvent.type(screen.getByLabelText(/confirm/i), "a long enough passphrase");
    await userEvent.click(screen.getByRole("button", { name: /set new password/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or has expired/i);
    expect(screen.getByRole("link", { name: /request a new link/i })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("explains a missing token instead of rendering a form that cannot work", () => {
    render(<ResetPasswordForm token={null} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/link is missing or incomplete/i);
    expect(screen.queryByRole("button", { name: /set new password/i })).not.toBeInTheDocument();
  });
});
