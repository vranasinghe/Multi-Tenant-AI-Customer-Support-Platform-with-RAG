"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import { useAuth } from "@/lib/auth/auth-context";

import { PageLoading } from "./guards";

type Result = { status: "verifying" } | { status: "done" } | { status: "failed"; message: string };

export function VerifyEmail({ token }: { token: string | null }) {
  const { refresh } = useAuth();
  const [result, setResult] = useState<Result>({ status: "verifying" });
  const started = useRef(false);

  useEffect(() => {
    // Tokens are single-use: guard against React Strict Mode's double effect in development.
    if (!token || started.current) return;
    started.current = true;
    api
      .verifyEmail(token)
      .then(async () => {
        setResult({ status: "done" });
        await refresh(); // clears the "verify your email" banner if this browser is signed in
      })
      .catch((error: unknown) => setResult({ status: "failed", message: describeApiError(error) }));
  }, [token, refresh]);

  if (!token) {
    return <Alert variant="destructive">This verification link is missing or incomplete.</Alert>;
  }
  if (result.status === "verifying") return <PageLoading label="Verifying your email…" />;
  if (result.status === "failed") {
    return (
      <div className="grid gap-4">
        <Alert variant="destructive">{result.message}</Alert>
        <p className="text-sm text-muted-foreground">
          Sign in and use &ldquo;Resend verification email&rdquo; to get a new link.
        </p>
        <Button asChild variant="outline">
          <Link href="/login">Go to sign in</Link>
        </Button>
      </div>
    );
  }
  return (
    <div className="grid gap-4">
      <Alert variant="success">Email verified. Thanks, you&apos;re all set.</Alert>
      <Button asChild>
        <Link href="/dashboard">Continue</Link>
      </Button>
    </div>
  );
}
