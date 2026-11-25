"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { Org } from "@/lib/api/types";
import { storeOrgId } from "@/lib/orgs";

import { PageLoading } from "../auth/guards";

interface OrgContextValue {
  org: Org;
  reload: () => Promise<void>;
  setOrg: (org: Org) => void;
}

const OrgContext = createContext<OrgContextValue | null>(null);

type State =
  | { status: "loading" }
  | { status: "missing" }
  | { status: "error"; message: string }
  | { status: "ready"; org: Org };

async function loadOrgState(orgId: string): Promise<State> {
  try {
    const org = await api.getOrg(orgId);
    storeOrgId(org.id);
    return { status: "ready", org };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { status: "missing" };
    return { status: "error", message: describeApiError(error) };
  }
}

/**
 * Loads the org named in the URL *from the API*, which only answers if the signed-in user is a
 * member (404 otherwise, identical for "doesn't exist"). The role and permission list it returns
 * drive what the UI shows; the API still enforces every action.
 */
export function OrgProvider({ orgId, children }: { orgId: string; children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async () => {
    setState(await loadOrgState(orgId));
  }, [orgId]);

  useEffect(() => {
    // The layout keys this provider by org id, so switching orgs remounts it and never shows
    // the previous org's data while the next one loads.
    let active = true;
    void loadOrgState(orgId).then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, [orgId]);

  const value = useMemo<OrgContextValue | null>(
    () =>
      state.status === "ready"
        ? { org: state.org, reload: load, setOrg: (org) => setState({ status: "ready", org }) }
        : null,
    [state, load],
  );

  if (state.status === "loading") return <PageLoading label="Loading organization…" />;
  if (state.status === "missing") {
    return (
      <div className="grid max-w-md gap-3 py-8">
        <h1 className="text-xl font-semibold">Organization not found</h1>
        <p className="text-sm text-muted-foreground">
          It doesn&apos;t exist, or you&apos;re not a member of it.
        </p>
        <Button asChild variant="outline" className="justify-self-start">
          <Link href="/dashboard">Go to your organizations</Link>
        </Button>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="grid max-w-md gap-3 py-8">
        <Alert variant="destructive">{state.message}</Alert>
        <Button variant="outline" className="justify-self-start" onClick={() => void load()}>
          Try again
        </Button>
      </div>
    );
  }
  return <OrgContext value={value}>{children}</OrgContext>;
}

export function useOrg(): OrgContextValue {
  const context = useContext(OrgContext);
  if (!context) throw new Error("useOrg must be used inside <OrgProvider>");
  return context;
}
