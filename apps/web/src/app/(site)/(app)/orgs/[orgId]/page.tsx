"use client";

import { OverviewDashboard } from "@/components/overview/overview-dashboard";
import { useOrg } from "@/components/orgs/org-provider";

export default function OrgOverviewPage() {
  const { org } = useOrg();
  return <OverviewDashboard org={org} />;
}
