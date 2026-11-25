"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import type { ReactNode } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { useAuth } from "@/lib/auth/auth-context";
import { safeRedirectPath } from "@/lib/safe-redirect";

export function PageLoading({ label }: { label: string }) {
  return (
    <div
      role="status"
      className="flex min-h-40 items-center justify-center text-sm text-muted-foreground"
    >
      {label}
    </div>
  );
}

/**
 * Hides protected UI until `/me` confirms a session, and sends anonymous visitors to /login.
 * This is a UX convenience, not a security boundary: the API rejects unauthenticated calls
 * regardless of what the browser renders.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { state, refresh } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams().toString();

  useEffect(() => {
    if (state.status === "anonymous") {
      const target = search ? `${pathname}?${search}` : pathname;
      router.replace(`/login?next=${encodeURIComponent(target)}`);
    }
  }, [state.status, pathname, search, router]);

  if (state.status === "authenticated") return <>{children}</>;
  if (state.status === "error") {
    return (
      <div className="mx-auto flex max-w-md flex-col gap-3 py-16">
        <Alert variant="destructive">{state.message}</Alert>
        <Button variant="outline" onClick={() => void refresh()}>
          Try again
        </Button>
      </div>
    );
  }
  return <PageLoading label="Checking your session…" />;
}

/** For login/signup/forgot-password: signed-in users go straight on to the app. */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");

  useEffect(() => {
    if (state.status === "authenticated") router.replace(safeRedirectPath(next));
  }, [state.status, next, router]);

  if (state.status === "authenticated") return <PageLoading label="Redirecting…" />;
  return <>{children}</>;
}
