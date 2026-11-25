"use client";

import { KnowledgeScreen } from "@/components/knowledge/knowledge-screen";
import { useOrg } from "@/components/orgs/org-provider";

export default function KnowledgePage() {
  const { org } = useOrg();
  return <KnowledgeScreen org={org} />;
}
