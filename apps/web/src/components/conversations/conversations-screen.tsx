"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Button } from "@acs/ui/components/button";
import { Input } from "@acs/ui/components/input";
import { Select } from "@acs/ui/components/select";

import { ChatIcon, SearchIcon } from "@/components/kit/icons";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/kit/states";
import { api } from "@/lib/api";
import type { ConversationStatus, InboxFilters, Org } from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

import { ConversationStatusBadge, formatWhen, handoffLabel } from "./conversation-status";

export function ConversationsScreen({ org }: { org: Org }) {
  const base = `/orgs/${encodeURIComponent(org.id)}`;
  const [q, setQ] = useState("");
  const [chatbotId, setChatbotId] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [extra, setExtra] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const bots = useAsyncData(() => api.listChatbots(org.id), [org.id]);

  const filters = useMemo<InboxFilters>(() => {
    const next: InboxFilters = { q, limit: 25, cursor };
    if (chatbotId) next.chatbot_id = chatbotId;
    if (channel) next.channel = channel as InboxFilters["channel"];
    if (status) next.status = status as ConversationStatus;
    if (from) next.from = new Date(from).toISOString();
    if (to) next.to = new Date(`${to}T23:59:59`).toISOString();
    if (extra === "negative") next.feedback = "negative";
    if (extra === "positive") next.feedback = "positive";
    if (extra === "unanswered") next.unanswered = true;
    if (extra === "ungrounded") next.grounded = false;
    if (extra === "csat-low") next.satisfaction = "negative";
    return next;
  }, [q, chatbotId, channel, status, from, to, extra, cursor]);

  const { data, error, reload } = useAsyncData(
    () => api.listInbox(org.id, filters),
    [org.id, q, chatbotId, channel, status, from, to, extra, cursor],
  );

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Conversations"
        description="Review what customers ask, how your chatbots answer, and where a human needs to step in. Resolution is set by your team — not by whether the AI replied."
      />

      <form
        role="search"
        aria-label="Conversation filters"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="relative lg:col-span-2">
          <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground">
            <SearchIcon />
          </span>
          <Input
            type="search"
            aria-label="Search conversations"
            placeholder="Search messages"
            value={q}
            onChange={(event) => {
              setCursor(null);
              setQ(event.target.value);
            }}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Chatbot"
          value={chatbotId}
          onChange={(event) => {
            setCursor(null);
            setChatbotId(event.target.value);
          }}
        >
          <option value="">All chatbots</option>
          {bots.data?.data.map((bot) => (
            <option key={bot.id} value={bot.id}>
              {bot.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Channel"
          value={channel}
          onChange={(event) => {
            setCursor(null);
            setChannel(event.target.value);
          }}
        >
          <option value="">All channels</option>
          <option value="widget">Widget</option>
          <option value="playground">Playground</option>
        </Select>
        <Select
          aria-label="Status"
          value={status}
          onChange={(event) => {
            setCursor(null);
            setStatus(event.target.value);
          }}
        >
          <option value="">Any status</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
          <option value="unresolved">Unresolved</option>
          <option value="handed_off">Handed off</option>
        </Select>
        <Select
          aria-label="Flags"
          value={extra}
          onChange={(event) => {
            setCursor(null);
            setExtra(event.target.value);
          }}
        >
          <option value="">Any flags</option>
          <option value="negative">Negative answer feedback</option>
          <option value="positive">Positive answer feedback</option>
          <option value="unanswered">Unanswered questions</option>
          <option value="ungrounded">Ungrounded replies</option>
          <option value="csat-low">Low satisfaction</option>
        </Select>
        <Input
          type="date"
          aria-label="From date"
          value={from}
          onChange={(event) => {
            setCursor(null);
            setFrom(event.target.value);
          }}
        />
        <Input
          type="date"
          aria-label="To date"
          value={to}
          onChange={(event) => {
            setCursor(null);
            setTo(event.target.value);
          }}
        />
      </form>

      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <ListSkeleton label="Loading conversations…" rows={5} />
      ) : data.data.length === 0 ? (
        <EmptyState
          icon={<ChatIcon />}
          title="No conversations yet"
          description="Conversations appear here once customers chat in the widget or you test in the playground. Playground threads are listed, but they are excluded from analytics."
        />
      ) : (
        <div className="grid gap-3">
          <p className="text-sm text-muted-foreground">{data.total} conversations</p>
          <ul className="grid gap-2" aria-label="Conversations">
            {data.data.map((row) => (
              <li key={row.id}>
                <Link
                  href={`${base}/conversations/${encodeURIComponent(row.id)}`}
                  className="grid gap-2 rounded-xl border bg-card p-4 hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium text-pretty">{row.preview || "Empty conversation"}</p>
                    <ConversationStatusBadge status={row.status} />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {row.chatbot_name} · {row.channel} · {formatWhen(row.last_message_at)}
                    {row.unanswered_count > 0 ? ` · ${row.unanswered_count} unanswered` : ""}
                    {handoffLabel(row.handoff_status)
                      ? ` · ${handoffLabel(row.handoff_status)}`
                      : ""}
                    {row.satisfaction_score ? ` · CSAT ${row.satisfaction_score}/5` : ""}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
          {data.has_more && (
            <Button
              type="button"
              variant="outline"
              className="justify-self-start"
              onClick={() => setCursor(data.next_cursor)}
            >
              Load more
            </Button>
          )}
        </div>
      )}

      {can(org, "analytics:read") && (
        <p className="text-sm text-muted-foreground">
          Usage and quality metrics live on{" "}
          <Link href={`${base}/analytics`} className="underline-offset-4 hover:underline">
            Analytics
          </Link>
          .
        </p>
      )}
    </div>
  );
}
