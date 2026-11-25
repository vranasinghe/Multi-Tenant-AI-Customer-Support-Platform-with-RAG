// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";

const mocks = vi.hoisted(() => ({ verifyEmail: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: { verifyEmail: mocks.verifyEmail } };
});
vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({
    state: { status: "anonymous" },
    refresh: mocks.refresh,
    setSession: vi.fn(),
    signOut: vi.fn(),
  }),
}));

import { VerifyEmail } from "./verify-email";

beforeEach(() => {
  mocks.verifyEmail.mockReset();
  mocks.refresh.mockReset();
});

describe("VerifyEmail", () => {
  it("consumes the token once and confirms", async () => {
    mocks.verifyEmail.mockResolvedValue({ status: "verified" });
    const token = "v".repeat(43);

    render(<VerifyEmail token={token} />);

    expect(screen.getByRole("status")).toHaveTextContent(/verifying/i);
    expect(await screen.findByText(/email verified/i)).toBeInTheDocument();
    expect(mocks.verifyEmail).toHaveBeenCalledExactlyOnceWith(token);
    expect(mocks.refresh).toHaveBeenCalled(); // so the "verify your email" banner clears
  });

  it("explains a dead link", async () => {
    mocks.verifyEmail.mockRejectedValue(
      new ApiError({ status: 400, code: "invalid_token", message: "x" }),
    );

    render(<VerifyEmail token={"v".repeat(43)} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid or has expired/i);
  });

  it("explains a link with no token and never calls the API", () => {
    render(<VerifyEmail token={null} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/missing or incomplete/i);
    expect(mocks.verifyEmail).not.toHaveBeenCalled();
  });
});
