"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import type { MeResponse, OrgRole, User } from "@/lib/api/types";

/**
 * Client-side view of "who am I". The API is the only authority: this state is a cache of
 * `GET /me`, re-fetched on load and after auth changes. The session cookie is HttpOnly, so the
 * browser can't (and needn't) inspect it. UI gating is cosmetic; every request is re-authorized
 * server-side.
 */
export type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error"; message: string }
  | { status: "authenticated"; user: User; orgs: OrgRole[] };

interface AuthContextValue {
  state: AuthState;
  /** Adopt a `/me`-shaped response (e.g. from login) without another round trip. */
  setSession: (me: MeResponse) => void;
  /** Re-check the session; resolves with the resulting state. */
  refresh: () => Promise<AuthState>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function loadAuthState(): Promise<AuthState> {
  try {
    const me = await api.me();
    return { status: "authenticated", user: me.user, orgs: me.orgs };
  } catch (error) {
    if (error instanceof ApiError && error.isUnauthenticated) return { status: "anonymous" };
    return {
      status: "error",
      message: error instanceof ApiError ? error.message : "Something went wrong. Try again.",
    };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const refresh = useCallback(async (): Promise<AuthState> => {
    const next = await loadAuthState();
    setState(next);
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    void loadAuthState().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, []);

  const setSession = useCallback((me: MeResponse) => {
    setState({ status: "authenticated", user: me.user, orgs: me.orgs });
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // Even if the server is unreachable we drop local state; the cookie is HttpOnly and
      // expires server-side regardless.
    }
    setState({ status: "anonymous" });
  }, []);

  const value = useMemo(
    () => ({ state, setSession, refresh, signOut }),
    [state, setSession, refresh, signOut],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
