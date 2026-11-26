"use client";

import { useMemo, useState } from "react";

import { Button } from "@acs/ui/components/button";
import { Input } from "@acs/ui/components/input";
import { Select } from "@acs/ui/components/select";

import { ChartIcon } from "@/components/kit/icons";
import { EmptyState, ErrorState, PageHeader, StatSkeleton } from "@/components/kit/states";
import { formatRate } from "@/components/conversations/conversation-status";
import { api } from "@/lib/api";
import type { Org } from "@/lib/api/types";
import { describeApiError } from "@/lib/api/messages";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

function formatDay(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function BarChart({
  points,
  label,
  empty,
}: {
  points: { t: string; value: number }[];
  label: string;
  empty: string;
}) {
  if (points.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  const max = Math.max(...points.map((point) => point.value), 1);
  return (
    <div role="img" aria-label={label} className="flex h-40 items-end gap-1">
      {points.map((point) => (
        <div key={point.t} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1">
          <div
            className="w-full rounded-t bg-primary/80"
            style={{ height: `${Math.max(4, (point.value / max) * 100)}%` }}
            title={`${formatDay(point.t)}: ${point.value}`}
          />
          <span className="w-full truncate text-center text-[10px] text-muted-foreground">
            {formatDay(point.t)}
          </span>
        </div>
      ))}
    </div>
  );
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="grid gap-1 rounded-xl border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-pretty text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function AnalyticsDashboard({ org }: { org: Org }) {
  const [chatbotId, setChatbotId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const bots = useAsyncData(() => api.listChatbots(org.id), [org.id]);
  const filters = useMemo(
    () => ({
      chatbot_id: chatbotId || undefined,
      from: from ? new Date(from).toISOString() : undefined,
      to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
    }),
    [chatbotId, from, to],
  );
  const summary = useAsyncData(
    () => api.analyticsSummary(org.id, filters),
    [org.id, chatbotId, from, to],
  );
  const daily = useAsyncData(
    () => api.analyticsTimeseries(org.id, "conversations", "day", filters),
    [org.id, chatbotId, from, to],
  );
  const monthly = useAsyncData(
    () => api.analyticsTimeseries(org.id, "conversations", "month", filters),
    [org.id, chatbotId, from, to],
  );
  const tokens = useAsyncData(
    () => api.analyticsTimeseries(org.id, "tokens", "day", filters),
    [org.id, chatbotId, from, to],
  );
  const gaps = useAsyncData(
    () => api.listKnowledgeGaps(org.id, chatbotId || undefined),
    [org.id, chatbotId],
  );
  const data = summary.data;

  async function exportCsv() {
    if (!can(org, "conversation:export")) return;
    setExporting(true);
    setExportError(null);
    try {
      const created = await api.createConversationExport(org.id, {
        chatbot_id: chatbotId || undefined,
        from_at: filters.from,
        to_at: filters.to,
      });
      const blob = await api.downloadConversationExport(org.id, created.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `conversations-${created.id}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (failure) {
      setExportError(describeApiError(failure));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Analytics"
        description="Product metrics from stored conversations and events. Playground tests are excluded from rates; token usage still includes them."
        actions={
          can(org, "conversation:export") ? (
            <Button
              type="button"
              variant="outline"
              disabled={exporting}
              onClick={() => void exportCsv()}
            >
              {exporting ? "Exporting…" : "Export CSV"}
            </Button>
          ) : undefined
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
      </div>
      {exportError && (
        <p role="alert" className="text-sm text-destructive">
          {exportError}
        </p>
      )}

      {summary.error ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : !data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatSkeleton />
          <StatSkeleton />
          <StatSkeleton />
          <StatSkeleton />
        </div>
      ) : data.conversations === 0 && data.charged_tokens === 0 ? (
        <EmptyState
          icon={<ChartIcon />}
          title="No analytics yet"
          description="Charts fill in from widget and messaging conversations. Playground usage can still appear under tokens and estimated cost."
        />
      ) : (
        <>
          <section
            aria-labelledby="kpis-heading"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <h2 id="kpis-heading" className="sr-only">
              Summary
            </h2>
            <MetricCard
              label="Conversations"
              value={String(data.conversations)}
              hint="Production channels only"
            />
            <MetricCard
              label="Resolution rate"
              value={formatRate(data.resolution_rate)}
              hint={data.definitions.resolution_rate}
            />
            <MetricCard
              label="Satisfaction rate"
              value={formatRate(data.satisfaction_rate)}
              hint={data.definitions.satisfaction_rate}
            />
            <MetricCard
              label="Grounded rate"
              value={formatRate(data.grounded_rate)}
              hint={data.definitions.grounded_rate}
            />
            <MetricCard
              label="Unanswered"
              value={String(data.unanswered)}
              hint={data.definitions.playground}
            />
            <MetricCard
              label="Estimated AI cost"
              value={`$${Number(data.estimated_cost_usd).toFixed(4)}`}
              hint="Estimate from recorded token usage. Includes playground."
            />
            <MetricCard label="Tokens charged" value={data.charged_tokens.toLocaleString()} />
            <MetricCard
              label="Latency p95"
              value={data.latency_p95_ms == null ? "—" : `${data.latency_p95_ms} ms`}
            />
          </section>

          <section
            aria-labelledby="daily-heading"
            className="grid gap-3 rounded-xl border bg-card p-5"
          >
            <h2 id="daily-heading" className="font-semibold">
              Conversations by day
            </h2>
            {daily.error ? (
              <ErrorState message={daily.error} onRetry={daily.reload} />
            ) : (
              <BarChart
                points={daily.data?.points ?? []}
                label="Daily conversations"
                empty="No daily conversation volume in this range."
              />
            )}
          </section>

          <section
            aria-labelledby="monthly-heading"
            className="grid gap-3 rounded-xl border bg-card p-5"
          >
            <h2 id="monthly-heading" className="font-semibold">
              Conversations by month
            </h2>
            {monthly.error ? (
              <ErrorState message={monthly.error} onRetry={monthly.reload} />
            ) : (
              <BarChart
                points={monthly.data?.points ?? []}
                label="Monthly conversations"
                empty="No monthly conversation volume in this range."
              />
            )}
          </section>

          <section
            aria-labelledby="tokens-heading"
            className="grid gap-3 rounded-xl border bg-card p-5"
          >
            <h2 id="tokens-heading" className="font-semibold">
              Token usage by day
            </h2>
            {tokens.error ? (
              <ErrorState message={tokens.error} onRetry={tokens.reload} />
            ) : (
              <BarChart
                points={tokens.data?.points ?? []}
                label="Daily tokens"
                empty="No token usage in this range."
              />
            )}
          </section>

          <section aria-labelledby="bots-heading" className="grid gap-3">
            <h2 id="bots-heading" className="font-semibold">
              Chatbot comparison
            </h2>
            {data.chatbots.length === 0 ? (
              <p className="text-sm text-muted-foreground">No chatbot activity in this range.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border">
                <table className="w-full min-w-[40rem] text-left text-sm">
                  <thead className="bg-muted/40 text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">Chatbot</th>
                      <th className="px-3 py-2 font-medium">Conversations</th>
                      <th className="px-3 py-2 font-medium">Resolution</th>
                      <th className="px-3 py-2 font-medium">Satisfaction</th>
                      <th className="px-3 py-2 font-medium">Grounded</th>
                      <th className="px-3 py-2 font-medium">Est. cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.chatbots.map((bot) => (
                      <tr key={bot.chatbot_id} className="border-t">
                        <td className="px-3 py-2">{bot.chatbot_name}</td>
                        <td className="px-3 py-2 tabular-nums">{bot.conversations}</td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatRate(bot.resolution_rate)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          {formatRate(bot.satisfaction_rate)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">{formatRate(bot.grounded_rate)}</td>
                        <td className="px-3 py-2 tabular-nums">
                          ${Number(bot.estimated_cost_usd).toFixed(4)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      <section aria-labelledby="gaps-heading" className="grid gap-3">
        <h2 id="gaps-heading" className="font-semibold">
          Knowledge gaps
        </h2>
        <p className="text-sm text-muted-foreground">
          Grouped from unanswered-question events, not from inferred “the bot answered.”
        </p>
        {gaps.error ? (
          <ErrorState message={gaps.error} onRetry={gaps.reload} />
        ) : !gaps.data ? (
          <StatSkeleton />
        ) : gaps.data.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No unanswered questions recorded yet.</p>
        ) : (
          <ul className="grid gap-2" aria-label="Knowledge gaps">
            {gaps.data.data.map((gap) => (
              <li
                key={`${gap.chatbot_id}-${gap.cluster_key}`}
                className="rounded-xl border bg-card p-4"
              >
                <p className="font-medium text-pretty">{gap.representative}</p>
                <p className="text-sm text-muted-foreground">
                  {gap.chatbot_name} · asked {gap.count} times
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
