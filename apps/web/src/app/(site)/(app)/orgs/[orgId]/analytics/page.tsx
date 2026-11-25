"use client";

import { ChartIcon } from "@/components/kit/icons";
import { ComingSoon, EmptyState, PageHeader, PlaceholderBadge } from "@/components/kit/states";

const PLANNED_METRICS = [
  "Conversations and messages over time",
  "Answer (grounded) rate",
  "Thumbs up / down ratio",
  "Response latency (p95)",
  "Channel split: widget, Telegram, WhatsApp",
  "Top unanswered questions",
];

export default function AnalyticsPage() {
  return (
    <div className="grid gap-6">
      <PageHeader
        title="Analytics"
        description="How much your chatbots are used and how well they answer."
        actions={<PlaceholderBadge phase="Analytics phase" />}
      />
      <EmptyState
        icon={<ChartIcon />}
        title="No analytics yet"
        description="Charts appear once conversations are being captured. No numbers are shown until then."
      />
      <ComingSoon
        title="Planned dashboard"
        phase="Analytics phase"
        description="Daily rollups computed from real conversation data, filterable by chatbot and date range."
      >
        <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {PLANNED_METRICS.map((metric) => (
            <li key={metric} className="rounded-lg border bg-background px-3 py-2">
              {metric}
            </li>
          ))}
        </ul>
      </ComingSoon>
    </div>
  );
}
