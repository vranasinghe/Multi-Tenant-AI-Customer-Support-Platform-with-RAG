"use client";

import Link from "next/link";

import { Button } from "@acs/ui/components/button";

import { ChatbotWizard } from "@/components/chatbots/chatbot-wizard";
import { ArrowLeftIcon } from "@/components/kit/icons";
import { ErrorState, ListSkeleton, PageHeader } from "@/components/kit/states";
import { useOrg } from "@/components/orgs/org-provider";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth/auth-context";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

export default function NewChatbotPage() {
  const { org } = useOrg();
  const { state } = useAuth();
  const { data: options, error, reload } = useAsyncData(() => api.chatbotOptions(org.id), [org.id]);
  const back = `/orgs/${encodeURIComponent(org.id)}/chatbots`;
  const verified = state.status === "authenticated" && state.user.email_verified;

  let body;
  if (!can(org, "chatbot:write") || org.status !== "active") {
    body = (
      <ErrorState
        title="You can't create chatbots here"
        message={
          org.status !== "active"
            ? "This organization is read-only right now."
            : "Your role is view-only. Ask an admin or agent to create a chatbot."
        }
      />
    );
  } else if (!verified) {
    body = (
      <ErrorState
        title="Verify your email first"
        message="Creating chatbots requires a verified email address. Use the banner above to resend the link."
      />
    );
  } else if (error) {
    body = <ErrorState message={error} onRetry={reload} />;
  } else if (!options) {
    body = <ListSkeleton rows={2} label="Loading setup…" />;
  } else {
    body = <ChatbotWizard org={org} options={options} />;
  }

  return (
    <div className="grid gap-8">
      <PageHeader
        eyebrow={
          <Button asChild variant="link" className="h-auto justify-start p-0 text-muted-foreground">
            <Link href={back}>
              <ArrowLeftIcon />
              All chatbots
            </Link>
          </Button>
        }
        title="Create a chatbot"
        description="Five short steps. Everything can be changed later in the chatbot's settings."
      />
      {body}
    </div>
  );
}
