"use client";

import { Input } from "@acs/ui/components/input";
import { Select } from "@acs/ui/components/select";

import { ChatIcon, SearchIcon } from "@/components/kit/icons";
import { ComingSoon, EmptyState, PageHeader, PlaceholderBadge } from "@/components/kit/states";
import { api } from "@/lib/api";
import type { Org } from "@/lib/api/types";
import { useAsyncData } from "@/lib/use-async-data";

/**
 * Conversation management. The chatbot filter is populated from live data; conversations
 * themselves are captured once chat ships, so the list is an honest empty state, not sample rows.
 */
export function ConversationsScreen({ org }: { org: Org }) {
  const { data } = useAsyncData(() => api.listChatbots(org.id), [org.id]);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Conversations"
        description="Review what customers ask, how your chatbots answer, and where knowledge is missing."
        actions={<PlaceholderBadge phase="Chat phase" />}
      />

      <div
        role="group"
        aria-label="Conversation filters (available when conversations are captured)"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      >
        <div className="relative lg:col-span-2">
          <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground">
            <SearchIcon />
          </span>
          <Input
            disabled
            type="search"
            aria-label="Search conversations"
            placeholder="Search messages"
            className="pl-9"
          />
        </div>
        <Select disabled aria-label="Chatbot" defaultValue="">
          <option value="">All chatbots</option>
          {data?.data.map((bot) => (
            <option key={bot.id} value={bot.id}>
              {bot.name}
            </option>
          ))}
        </Select>
        <Select disabled aria-label="Feedback" defaultValue="">
          <option value="">Any feedback</option>
          <option value="negative">Negative feedback</option>
          <option value="ungrounded">Unanswered</option>
        </Select>
      </div>

      <EmptyState
        icon={<ChatIcon />}
        title="No conversations yet"
        description="Conversations appear here once your chatbots start answering in the playground, widget or messaging channels."
      />

      <ComingSoon
        title="Transcripts, feedback and unanswered questions"
        phase="Chat & analytics phases"
        description="Full transcripts with cited sources, thumbs up/down feedback, grouped unanswered questions, conversation deletion and CSV export."
      />
    </div>
  );
}
