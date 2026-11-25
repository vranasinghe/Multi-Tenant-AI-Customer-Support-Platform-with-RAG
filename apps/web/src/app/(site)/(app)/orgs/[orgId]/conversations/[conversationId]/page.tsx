"use client";

import { useParams } from "next/navigation";

import { ConversationDetailScreen } from "@/components/conversations/conversation-detail";
import { useOrg } from "@/components/orgs/org-provider";

export default function ConversationDetailPage() {
  const { org } = useOrg();
  const params = useParams<{ conversationId: string }>();
  return <ConversationDetailScreen org={org} conversationId={params.conversationId} />;
}
