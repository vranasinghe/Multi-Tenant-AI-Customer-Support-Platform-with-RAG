"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@acs/ui/components/button";

import { PageLoading } from "@/components/auth/guards";
import { useAuth } from "@/lib/auth/auth-context";
import { readStoredOrgId, resolveActiveOrgId } from "@/lib/orgs";

/** Landing spot after sign-in: re-reads memberships, then opens the remembered (or first) org. */
export default function DashboardPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [hasNoOrgs, setHasNoOrgs] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void refresh().then((state) => {
      if (cancelled || state.status !== "authenticated") return;
      const orgId = resolveActiveOrgId(state.orgs, { storedOrgId: readStoredOrgId() });
      if (orgId) router.replace(`/orgs/${encodeURIComponent(orgId)}`);
      else setHasNoOrgs(true);
    });
    return () => {
      cancelled = true;
    };
  }, [refresh, router]);

  if (!hasNoOrgs) return <PageLoading label="Opening your organization…" />;
  return (
    <div className="grid max-w-md gap-3">
      <h1 className="text-xl font-semibold">You&apos;re not in any organization yet</h1>
      <p className="text-sm text-muted-foreground">
        Create one, or ask a teammate to send you an invitation.
      </p>
      <Button asChild className="justify-self-start">
        <Link href="/orgs/new">Create an organization</Link>
      </Button>
    </div>
  );
}
