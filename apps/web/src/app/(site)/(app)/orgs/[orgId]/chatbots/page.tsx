"use client";

import { ChatbotList } from "@/components/chatbots/chatbot-list";
import { useOrg } from "@/components/orgs/org-provider";

export default function ChatbotsPage() {
  const { org } = useOrg();
  return <ChatbotList org={org} />;
}
