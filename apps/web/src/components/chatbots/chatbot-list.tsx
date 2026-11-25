"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@acs/ui/components/button";
import { Input } from "@acs/ui/components/input";
import { Select } from "@acs/ui/components/select";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { Chatbot, ChatbotStatus, Org } from "@/lib/api/types";
import { STATUS_META } from "@/lib/chatbots";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

import { ConfirmDialog } from "../kit/confirm-dialog";
import { BotIcon, PlusIcon, SearchIcon, TrashIcon } from "../kit/icons";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "../kit/states";
import { useToast } from "../kit/toast";
import { StatusBadge } from "./status-badge";
import { BotAvatar } from "./widget-preview";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function ChatbotList({ org }: { org: Org }) {
  const toast = useToast();
  const canWrite = can(org, "chatbot:write");
  const canDelete = can(org, "chatbot:delete");
  const base = `/orgs/${encodeURIComponent(org.id)}/chatbots`;

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ChatbotStatus | "">("");
  const query = useDebounced(search, 250);
  const [deleting, setDeleting] = useState<Chatbot | null>(null);

  const { data, error, reload, update } = useAsyncData(
    () => api.listChatbots(org.id, { status, q: query }),
    [org.id, status, query],
  );
  const filtered = Boolean(status || query.trim());
  const atLimit = data ? data.data.length >= data.limit && !filtered : false;

  async function confirmDelete() {
    if (!deleting) return;
    const bot = deleting;
    try {
      await api.deleteChatbot(org.id, bot.id);
      update(
        (current) => current && { ...current, data: current.data.filter((b) => b.id !== bot.id) },
      );
      setDeleting(null);
      toast.success("Chatbot deleted", `${bot.name} was removed.`);
    } catch (failure) {
      setDeleting(null);
      toast.error("Couldn't delete chatbot", describeApiError(failure));
    }
  }

  const createButton = canWrite ? (
    <Button asChild={!atLimit} disabled={atLimit}>
      {atLimit ? (
        <span>
          <PlusIcon />
          New chatbot
        </span>
      ) : (
        <Link href={`${base}/new`}>
          <PlusIcon />
          New chatbot
        </Link>
      )}
    </Button>
  ) : null;

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Chatbots"
        description="Create assistants, configure how they answer and manage their lifecycle."
        actions={createButton}
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground">
            <SearchIcon />
          </span>
          <Input
            type="search"
            aria-label="Search chatbots"
            placeholder="Search by name"
            value={search}
            maxLength={80}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Filter by status"
          value={status}
          onChange={(event) => setStatus(event.target.value as ChatbotStatus | "")}
          className="sm:w-44"
        >
          <option value="">All statuses</option>
          {(Object.keys(STATUS_META) as ChatbotStatus[]).map((value) => (
            <option key={value} value={value}>
              {STATUS_META[value].label}
            </option>
          ))}
        </Select>
      </div>

      {data && (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {filtered
            ? `${data.data.length} matching chatbot${data.data.length === 1 ? "" : "s"}`
            : `${data.data.length} of ${data.limit} chatbots used`}
          {atLimit && " · You've reached your plan's chatbot limit."}
        </p>
      )}

      {error ? (
        <ErrorState title="Couldn't load chatbots" message={error} onRetry={reload} />
      ) : data === null ? (
        <ListSkeleton label="Loading chatbots…" />
      ) : data.data.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={<SearchIcon />}
            title="No chatbots match"
            description="Try a different name or status filter."
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setSearch("");
                  setStatus("");
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<BotIcon />}
            title="No chatbots yet"
            description={
              canWrite
                ? "Create your first assistant. It takes about two minutes, and you can change everything later."
                : "Your team hasn't created any chatbots yet. Ask an admin or agent to create one."
            }
            action={
              canWrite ? (
                <Button asChild>
                  <Link href={`${base}/new`}>
                    <PlusIcon />
                    Create chatbot
                  </Link>
                </Button>
              ) : undefined
            }
          />
        )
      ) : (
        <ul className="grid gap-3" aria-label="Chatbots">
          {data.data.map((bot) => (
            <li
              key={bot.id}
              className="flex flex-col gap-4 rounded-xl border bg-card p-4 transition-colors hover:bg-muted/30 sm:flex-row sm:items-center"
            >
              <div className="flex min-w-0 flex-1 items-center gap-4">
                <BotAvatar
                  name={bot.name}
                  avatarUrl={bot.widget_settings.avatar_url}
                  color={bot.widget_settings.primary_color}
                />
                <div className="grid min-w-0 gap-0.5">
                  <Link
                    href={`${base}/${encodeURIComponent(bot.id)}`}
                    className="truncate font-medium outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    {bot.name}
                  </Link>
                  <p className="truncate text-sm text-muted-foreground">
                    {bot.description || "No description"}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground sm:justify-end">
                <StatusBadge status={bot.status} />
                <span className="hidden md:inline">{bot.model}</span>
                <span>
                  Updated{" "}
                  <time dateTime={bot.updated_at}>
                    {dateFormat.format(new Date(bot.updated_at))}
                  </time>
                </span>
                <div className="flex gap-1">
                  <Button asChild variant="outline" size="sm">
                    <Link href={`${base}/${encodeURIComponent(bot.id)}`}>
                      {canWrite ? "Edit" : "View"}
                      <span className="sr-only"> {bot.name}</span>
                    </Link>
                  </Button>
                  {canDelete && (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Delete ${bot.name}`}
                      onClick={() => setDeleting(bot)}
                    >
                      <TrashIcon />
                    </Button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "chatbot"}?`}
        description="It stops answering immediately, disappears from your workspace and its public key stops working. This can't be undone from the dashboard."
        confirmLabel="Delete chatbot"
        destructive
        onConfirm={confirmDelete}
      />
    </div>
  );
}
