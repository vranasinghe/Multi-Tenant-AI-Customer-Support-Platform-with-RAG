"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@acs/ui/components/button";
import { Input } from "@acs/ui/components/input";
import { Select } from "@acs/ui/components/select";

import { ChatIcon, SearchIcon } from "@/components/kit/icons";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/kit/states";
import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type {
  ConversationList,
  ConversationStatus,
  ConversationSummary,
  InboxFilters,
  Org,
} from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

import { ConversationStatusBadge, formatWhen, handoffLabel } from "./conversation-status";

export function ConversationsScreen({ org }: { org: Org }) {
  // Keyed by organization: filters, options and rows of one organization never reach another.
  return <Inbox key={org.id} org={org} />;
}

function Inbox({ org }: { org: Org }) {
  const base = `/orgs/${encodeURIComponent(org.id)}`;
  const [q, setQ] = useState("");
  const [chatbotId, setChatbotId] = useState("");
  const [channel, setChannel] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [extra, setExtra] = useState("");
  const bots = useAsyncData(() => api.listChatbots(org.id), [org.id]);

  const filters: InboxFilters = { q, limit: 25 };
  if (chatbotId) filters.chatbot_id = chatbotId;
  if (channel) filters.channel = channel as InboxFilters["channel"];
  if (status) filters.status = status as ConversationStatus;
  // Both ends are local days: a bare date would be read as midnight UTC.
  if (from) filters.from = new Date(`${from}T00:00:00`).toISOString();
  if (to) filters.to = new Date(`${to}T23:59:59`).toISOString();
  if (extra === "negative") filters.feedback = "negative";
  if (extra === "positive") filters.feedback = "positive";
  if (extra === "unanswered") filters.unanswered = true;
  if (extra === "ungrounded") filters.grounded = false;
  if (extra === "csat-low") filters.satisfaction = "negative";

  const filtered = Boolean(q.trim() || chatbotId || channel || status || from || to || extra);

  function clearFilters() {
    for (const set of [setQ, setChatbotId, setChannel, setStatus, setFrom, setTo, setExtra]) {
      set("");
    }
  }

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
            onChange={(event) => setQ(event.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Chatbot"
          value={chatbotId}
          onChange={(event) => setChatbotId(event.target.value)}
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
          onChange={(event) => setChannel(event.target.value)}
        >
          <option value="">All channels</option>
          <option value="widget">Widget</option>
          <option value="playground">Playground</option>
        </Select>
        <Select
          aria-label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <option value="">Any status</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
          <option value="unresolved">Unresolved</option>
          <option value="handed_off">Handed off</option>
        </Select>
        <Select aria-label="Flags" value={extra} onChange={(event) => setExtra(event.target.value)}>
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
          onChange={(event) => setFrom(event.target.value)}
        />
        <Input
          type="date"
          aria-label="To date"
          value={to}
          onChange={(event) => setTo(event.target.value)}
        />
      </form>

      {/* Remounted for every filter combination: earlier rows, pages and errors go at once,
          and a late answer for them has nowhere to land. */}
      <Results
        key={JSON.stringify(filters)}
        orgId={org.id}
        base={base}
        filters={filters}
        onClear={filtered ? clearFilters : null}
      />

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

function Results({
  orgId,
  base,
  filters,
  onClear,
}: {
  orgId: string;
  base: string;
  filters: InboxFilters;
  onClear: (() => void) | null;
}) {
  const first = useAsyncData(() => api.listInbox(orgId, filters), [orgId]);
  const [later, setLater] = useState<ConversationList[]>([]);
  const [loading, setLoading] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);

  if (first.error) return <ErrorState message={first.error} onRetry={first.reload} />;
  if (!first.data) return <ListSkeleton label="Loading conversations…" rows={5} />;

  if (first.data.data.length === 0) {
    return onClear ? (
      <EmptyState
        icon={<ChatIcon />}
        title="No matching conversations"
        description="Nothing stored matches these filters."
        action={
          <Button type="button" variant="outline" onClick={onClear}>
            Clear filters
          </Button>
        }
      />
    ) : (
      <EmptyState
        icon={<ChatIcon />}
        title="No conversations yet"
        description="Conversations appear here once customers chat in the widget or you test in the playground. Playground threads are listed, but they are excluded from analytics."
      />
    );
  }

  const pages = [first.data, ...later];
  const last = pages[pages.length - 1] ?? first.data;
  // A conversation that gets a new message while you browse can be returned by two pages.
  const rows = new Map<string, ConversationSummary>();
  for (const item of pages.flatMap((page) => page.data)) rows.set(item.id, item);

  async function loadMore() {
    setLoading(true);
    setMoreError(null);
    try {
      const page = await api.listInbox(orgId, { ...filters, cursor: last.next_cursor });
      setLater((current) => [...current, page]);
    } catch (failure) {
      setMoreError(describeApiError(failure));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">
        Showing {rows.size} of {Math.max(first.data.total, rows.size)} conversations, latest
        activity first
      </p>
      <ul className="grid gap-2" aria-label="Conversations">
        {[...rows.values()].map((row) => (
          <li key={row.id} className="min-w-0">
            <Link
              href={`${base}/conversations/${encodeURIComponent(row.id)}`}
              className="grid gap-2 rounded-xl border bg-card p-4 hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="min-w-0 font-medium text-pretty wrap-anywhere">
                  {row.preview || "Empty conversation"}
                </p>
                <ConversationStatusBadge status={row.status} />
              </div>
              <p className="text-sm text-muted-foreground">
                {row.chatbot_name} · {row.channel} · last message{" "}
                <time dateTime={row.last_message_at}>{formatWhen(row.last_message_at)}</time> ·
                started <time dateTime={row.created_at}>{formatWhen(row.created_at)}</time>
                {row.unanswered_count > 0 ? ` · ${row.unanswered_count} unanswered` : ""}
                {handoffLabel(row.handoff_status) ? ` · ${handoffLabel(row.handoff_status)}` : ""}
                {row.satisfaction_score ? ` · CSAT ${row.satisfaction_score}/5` : ""}
              </p>
            </Link>
          </li>
        ))}
      </ul>
      {moreError && (
        <p role="alert" className="text-sm text-destructive">
          {moreError}
        </p>
      )}
      {last.has_more && (
        <Button
          type="button"
          variant="outline"
          className="justify-self-start"
          disabled={loading}
          onClick={() => void loadMore()}
        >
          Load more
        </Button>
      )}
    </div>
  );
}
