// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AuthState } from "@/lib/auth/auth-context";

const nav = vi.hoisted(() => ({ replace: vi.fn(), pathname: "/orgs/o1/members", search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const auth = vi.hoisted(() => ({ state: { status: "loading" } as AuthState }));
vi.mock("@/lib/auth/auth-context", () => ({
  useAuth: () => ({ state: auth.state, refresh: vi.fn(), setSession: vi.fn(), signOut: vi.fn() }),
}));

import { RedirectIfAuthenticated, RequireAuth } from "./guards";

const authenticated: AuthState = {
  status: "authenticated",
  user: { id: "u1", email: "a@b.co", name: "A", email_verified: true, locale: "en" },
  orgs: [],
};

beforeEach(() => {
  nav.replace.mockReset();
  nav.pathname = "/orgs/o1/members";
  nav.search = "";
});

describe("RequireAuth", () => {
  it("shows an accessible loading state and no protected content while checking the session", () => {
    auth.state = { status: "loading" };

    render(
      <RequireAuth>
        <p>secret</p>
      </RequireAuth>,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/checking your session/i);
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("sends anonymous visitors to /login with the page they wanted", () => {
    auth.state = { status: "anonymous" };

    render(
      <RequireAuth>
        <p>secret</p>
      </RequireAuth>,
    );

    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(nav.replace).toHaveBeenCalledWith("/login?next=%2Forgs%2Fo1%2Fmembers");
  });

  it("renders protected content once authenticated", () => {
    auth.state = authenticated;

    render(
      <RequireAuth>
        <p>secret</p>
      </RequireAuth>,
    );

    expect(screen.getByText("secret")).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("offers a retry instead of redirecting when the session check failed", () => {
    auth.state = { status: "error", message: "Can't reach the server." };

    render(
      <RequireAuth>
        <p>secret</p>
      </RequireAuth>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Can't reach the server.");
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(nav.replace).not.toHaveBeenCalled();
  });
});

describe("RedirectIfAuthenticated", () => {
  it("renders the form for anonymous visitors", () => {
    auth.state = { status: "anonymous" };

    render(
      <RedirectIfAuthenticated>
        <p>login form</p>
      </RedirectIfAuthenticated>,
    );

    expect(screen.getByText("login form")).toBeInTheDocument();
  });

  it("sends signed-in users to the dashboard", () => {
    auth.state = authenticated;

    render(
      <RedirectIfAuthenticated>
        <p>login form</p>
      </RedirectIfAuthenticated>,
    );

    expect(nav.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("honours a safe ?next= and ignores an unsafe one", () => {
    auth.state = authenticated;
    nav.search = "next=%2Faccount";
    const { unmount } = render(
      <RedirectIfAuthenticated>
        <p>x</p>
      </RedirectIfAuthenticated>,
    );
    expect(nav.replace).toHaveBeenLastCalledWith("/account");
    unmount();

    nav.search = "next=https%3A%2F%2Fevil.example";
    render(
      <RedirectIfAuthenticated>
        <p>x</p>
      </RedirectIfAuthenticated>,
    );
    expect(nav.replace).toHaveBeenLastCalledWith("/dashboard");
  });
});
