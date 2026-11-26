"use client";

import { AnalyticsDashboard } from "@/components/analytics/analytics-dashboard";
import { useOrg } from "@/components/orgs/org-provider";

export default function AnalyticsPage() {
  const { org } = useOrg();
  return <AnalyticsDashboard org={org} />;
}
