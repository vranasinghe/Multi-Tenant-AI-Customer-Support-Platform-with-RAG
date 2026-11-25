// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { MeResponse } from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  me: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});

import { AuthProvider, useAuth } from "./auth-context";

const ME: MeResponse = {
  user: { id: "u1", email: "dana@acme.com", name: "Dana", email_verified: true, locale: "en" },
  orgs: [{ id: "o1", name: "Acme", role: "owner" }],
};

function Probe() {
  const { state, signOut } = useAuth();
  return (
    <div>
      <p data-testid="status">{state.status}</p>
      {state.status === "authenticated" && <p>Hello {state.user.name}</p>}
      {state.status === "error" && <p>{state.message}</p>}
      <button onClick={() => void signOut()}>sign out</button>
    </div>
  );
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

beforeEach(() => {
  mocks.me.mockReset();
  mocks.logout.mockReset();
});

describe("AuthProvider", () => {
  it("starts loading, then authenticated when /me succeeds", async () => {
    mocks.me.mockResolvedValue(ME);

    renderProbe();

    expect(screen.getByTestId("status")).toHaveTextContent("loading");
    expect(await screen.findByText("Hello Dana")).toBeInTheDocument();
  });

  it("is anonymous on 401 (no/expired/revoked session)", async () => {
    mocks.me.mockRejectedValue(
      new ApiError({ status: 401, code: "unauthenticated", message: "no" }),
    );

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
  });

  it("reports an error (not anonymous) when the API is unreachable, so users aren't bounced to login", async () => {
    mocks.me.mockRejectedValue(
      new ApiError({ status: 0, code: "network_error", message: "Can't reach the server." }),
    );

    renderProbe();

    expect(await screen.findByText("Can't reach the server.")).toBeInTheDocument();
    expect(screen.getByTestId("status")).toHaveTextContent("error");
  });

  it("signOut revokes server-side and always clears local state, even if the call fails", async () => {
    mocks.me.mockResolvedValue(ME);
    mocks.logout.mockRejectedValue(
      new ApiError({ status: 0, code: "network_error", message: "offline" }),
    );
    renderProbe();
    await screen.findByText("Hello Dana");

    await userEvent.click(screen.getByRole("button", { name: "sign out" }));

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("anonymous"));
    expect(mocks.logout).toHaveBeenCalledOnce();
  });
});
