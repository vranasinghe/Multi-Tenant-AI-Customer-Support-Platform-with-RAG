"use client";

import { ConversationsScreen } from "@/components/conversations/conversations-screen";
import { useOrg } from "@/components/orgs/org-provider";

export default function ConversationsPage() {
  const { org } = useOrg();
  return <ConversationsScreen org={org} />;
}
