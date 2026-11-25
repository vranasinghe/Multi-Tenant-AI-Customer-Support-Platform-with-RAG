import type { ReactNode } from "react";

import { OrgProvider } from "@/components/orgs/org-provider";

export default async function OrgLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ orgId: string }>;
}) {
  const { orgId } = await params;
  // `key` remounts the provider (and everything below) when the org changes, so one org's data
  // can never linger on screen while another loads.
  return (
    <OrgProvider key={orgId} orgId={orgId}>
      {children}
    </OrgProvider>
  );
}
