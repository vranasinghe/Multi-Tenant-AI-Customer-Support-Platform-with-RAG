"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { Button } from "@acs/ui/components/button";
import { cn } from "@acs/ui/lib/utils";

import { BotAvatar } from "@/components/chatbots/widget-preview";
import { StatusBadge } from "@/components/chatbots/status-badge";
import { BotIcon, CheckIcon, PlusIcon } from "@/components/kit/icons";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  PlaceholderBadge,
  StatSkeleton,
} from "@/components/kit/states";
import { api } from "@/lib/api";
import type { Org } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/auth-context";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

const ROLE_COPY: Record<string, string> = {
  owner: "Full control, including ownership transfer and billing.",
  admin: "Manage members, settings and everything below the owner.",
  agent: "Build and test chatbots and knowledge.",
  viewer: "Read-only access.",
};

function StatCard({
  label,
  value,
  detail,
  placeholder,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  placeholder?: string;
}) {
  return (
    <div
      className={cn(
        "grid gap-2 rounded-xl border bg-card p-5",
        placeholder && "border-dashed bg-muted/30",
      )}
    >
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
      {placeholder && <PlaceholderBadge phase={placeholder} />}
    </div>
  );
}

export function OverviewDashboard({ org }: { org: Org }) {
  const { state } = useAuth();
  const base = `/orgs/${encodeURIComponent(org.id)}`;
  const { data, error, reload } = useAsyncData(
    () =>
      Promise.all([
        api.listChatbots(org.id),
        api.listMembers(org.id),
        api.analyticsSummary(org.id),
      ]),
    [org.id],
  );
  const bots = data?.[0].data ?? [];
  const members = data?.[1].data ?? [];
  const analytics = data?.[2];
  const active = bots.filter((b) => b.status === "active").length;
  const verified = state.status === "authenticated" && state.user.email_verified;

  const checklist = [
    { done: verified, label: "Verify your email address", href: "/account" },
    { done: bots.length > 0, label: "Create your first chatbot", href: `${base}/chatbots/new` },
    { done: false, label: "Add documents or a website", href: `${base}/knowledge` },
    { done: active > 0, label: "Activate a chatbot", href: `${base}/chatbots` },
    { done: members.length > 1, label: "Invite a teammate", href: `${base}/members` },
  ];
  const completed = checklist.filter((item) => item.done).length;

  return (
    <div className="grid gap-8">
      <PageHeader
        title={org.name}
        description={
          <>
            You are {org.role === "admin" ? "an" : "a"}{" "}
            <strong className="text-foreground">{org.role}</strong>. {ROLE_COPY[org.role]}
          </>
        }
        actions={
          can(org, "chatbot:write") ? (
            <Button asChild>
              <Link href={`${base}/chatbots/new`}>
                <PlusIcon />
                New chatbot
              </Link>
            </Button>
          ) : undefined
        }
      />

      {org.status !== "active" && (
        <p className="text-sm text-destructive" role="status">
          This organization is {org.status.replace("_", " ")}; changes are disabled.
        </p>
      )}

      {error ? (
        <ErrorState title="Couldn't load your overview" message={error} onRetry={reload} />
      ) : (
        <>
          <section aria-label="Key numbers" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {data ? (
              <>
                <StatCard
                  label="Chatbots"
                  value={bots.length}
                  detail={`${active} active · ${data[0].limit} allowed on your plan`}
                />
                <StatCard
                  label="Team members"
                  value={members.length}
                  detail={
                    <Link href={`${base}/members`} className="underline-offset-4 hover:underline">
                      Manage team
                    </Link>
                  }
                />
              </>
            ) : (
              <>
                <StatSkeleton />
                <StatSkeleton />
              </>
            )}
            <StatCard
              label="Conversations (30 days)"
              value={analytics ? analytics.conversations : "—"}
              detail={
                <Link href={`${base}/conversations`} className="underline-offset-4 hover:underline">
                  Open inbox
                </Link>
              }
            />
            <StatCard
              label="Resolution rate"
              value={
                analytics?.resolution_rate == null
                  ? "—"
                  : `${Math.round(analytics.resolution_rate * 100)}%`
              }
              detail="Staff-marked resolved, not AI replies"
            />
          </section>

          <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
            <section aria-labelledby="recent-heading" className="grid content-start gap-3">
              <div className="flex items-center justify-between">
                <h2 id="recent-heading" className="font-semibold">
                  Recent chatbots
                </h2>
                <Link
                  href={`${base}/chatbots`}
                  className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  View all
                </Link>
              </div>
              {!data ? (
                <div className="grid gap-2">
                  <StatSkeleton />
                </div>
              ) : bots.length === 0 ? (
                <EmptyState
                  icon={<BotIcon />}
                  title="No chatbots yet"
                  description="Your chatbots will show up here once they're created."
                  action={
                    can(org, "chatbot:write") ? (
                      <Button asChild size="sm">
                        <Link href={`${base}/chatbots/new`}>Create chatbot</Link>
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                <ul className="divide-y rounded-xl border bg-card">
                  {bots.slice(0, 5).map((bot) => (
                    <li key={bot.id}>
                      <Link
                        href={`${base}/chatbots/${encodeURIComponent(bot.id)}`}
                        className="flex items-center gap-3 p-4 outline-none hover:bg-muted/30 focus-visible:ring-[3px] focus-visible:ring-ring/50"
                      >
                        <BotAvatar
                          name={bot.name}
                          avatarUrl={bot.widget_settings.avatar_url}
                          color={bot.widget_settings.primary_color}
                          size="sm"
                        />
                        <span className="min-w-0 flex-1 truncate font-medium">{bot.name}</span>
                        <StatusBadge status={bot.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section
              aria-labelledby="setup-heading"
              className="grid content-start gap-3 rounded-xl border bg-card p-5"
            >
              <div className="grid gap-1">
                <h2 id="setup-heading" className="font-semibold">
                  Getting started
                </h2>
                <p className="text-sm text-muted-foreground">
                  {completed} of {checklist.length} done
                </p>
                <div
                  className="h-1.5 overflow-hidden rounded-full bg-muted"
                  role="progressbar"
                  aria-label="Setup progress"
                  aria-valuemin={0}
                  aria-valuemax={checklist.length}
                  aria-valuenow={completed}
                >
                  <div
                    className="h-full rounded-full bg-primary transition-[width]"
                    style={{ width: `${(completed / checklist.length) * 100}%` }}
                  />
                </div>
              </div>
              <ul className="grid gap-1">
                {checklist.map((item) => (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "flex size-5 shrink-0 items-center justify-center rounded-full border",
                          item.done && "border-transparent bg-primary text-primary-foreground",
                        )}
                      >
                        {item.done && <CheckIcon width={12} height={12} />}
                      </span>
                      <span className={cn(item.done && "text-muted-foreground line-through")}>
                        {item.label}
                      </span>
                      <span className="sr-only">{item.done ? "(done)" : "(to do)"}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
