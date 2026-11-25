"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { InvitationPreview } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { storeOrgId } from "@/lib/orgs";

import { PageLoading } from "./guards";

type Lookup =
  | { status: "loading" }
  | { status: "ready"; preview: InvitationPreview }
  | { status: "dead"; message: string };

export function InviteAcceptance({ token }: { token: string | null }) {
  const router = useRouter();
  const { state, refresh, signOut } = useAuth();
  const [lookup, setLookup] = useState<Lookup>({ status: "loading" });
  const [error, setError] = useState<{ message: string; wrongAccount?: boolean } | null>(null);
  const [pending, setPending] = useState(false);
  const submitting = useRef(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api
      .lookupInvitation(token)
      .then((preview) => !cancelled && setLookup({ status: "ready", preview }))
      .catch(
        (failure: unknown) =>
          !cancelled && setLookup({ status: "dead", message: describeApiError(failure) }),
      );
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (!token) {
    return <Alert variant="destructive">This invitation link is missing or incomplete.</Alert>;
  }
  if (lookup.status === "loading") return <PageLoading label="Loading invitation…" />;
  if (lookup.status === "dead") {
    return (
      <Alert variant="destructive">
        {lookup.message} Ask the person who invited you to send a new one.
      </Alert>
    );
  }

  const { preview } = lookup;
  const back = encodeURIComponent(`/invite?token=${token}`);

  async function accept() {
    if (submitting.current || !token) return;
    submitting.current = true;
    setPending(true);
    setError(null);
    try {
      const org = await api.acceptInvitation(token);
      await refresh();
      storeOrgId(org.id);
      router.replace(`/orgs/${encodeURIComponent(org.id)}`);
    } catch (failure) {
      if (
        failure instanceof ApiError &&
        failure.code === "forbidden" &&
        state.status === "authenticated"
      ) {
        setError({
          wrongAccount: true,
          message: `This invitation was sent to ${preview.email_hint}, but you're signed in as ${state.user.email}. Sign out and use the invited address.`,
        });
      } else {
        setError({ message: describeApiError(failure) });
      }
      submitting.current = false;
      setPending(false);
    }
  }

  return (
    <div className="grid gap-5">
      <p className="text-sm">
        {preview.inviter_name ?? "A teammate"} invited you to join{" "}
        <strong className="font-semibold">{preview.org_name}</strong> as{" "}
        <strong className="font-semibold">{preview.role}</strong>. The invitation was sent to{" "}
        <span className="font-mono text-xs">{preview.email_hint}</span>.
      </p>

      {error && <Alert variant="destructive">{error.message}</Alert>}
      {error?.wrongAccount && (
        <Button variant="outline" onClick={() => void signOut()}>
          Sign out
        </Button>
      )}

      {state.status === "authenticated" && !error?.wrongAccount && (
        <Button onClick={() => void accept()} disabled={pending}>
          {pending ? "Joining…" : "Accept invitation"}
        </Button>
      )}

      {state.status === "anonymous" && (
        <div className="grid gap-2">
          <p className="text-sm text-muted-foreground">
            Sign in, or create an account, with the invited email address to continue.
          </p>
          <Button asChild>
            <Link href={`/login?next=${back}`}>Sign in</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={`/signup?next=${back}`}>Create an account</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
