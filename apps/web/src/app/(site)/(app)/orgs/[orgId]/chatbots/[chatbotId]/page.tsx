"use client";

import { useParams } from "next/navigation";

import { ChatbotEditorPage } from "@/components/chatbots/chatbot-editor";
import { useOrg } from "@/components/orgs/org-provider";

export default function ChatbotPage() {
  const { org } = useOrg();
  const { chatbotId } = useParams<{ chatbotId: string }>();
  return <ChatbotEditorPage org={org} chatbotId={chatbotId} />;
}
