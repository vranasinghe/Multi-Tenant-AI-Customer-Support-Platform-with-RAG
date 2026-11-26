import { cn } from "@acs/ui/lib/utils";

import type { ConversationStatus, HandoffStatus } from "@/lib/api/types";

const STATUS: Record<ConversationStatus, { label: string; className: string }> = {
  open: { label: "Open", className: "bg-muted-foreground/60" },
  resolved: { label: "Resolved", className: "bg-success" },
  unresolved: { label: "Unresolved", className: "bg-destructive" },
  handed_off: { label: "Handed off", className: "bg-amber-500" },
};

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  const meta = STATUS[status];
  return (
    <span
      role="status"
      aria-label={meta.label}
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium"
    >
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", meta.className)} />
      {meta.label}
    </span>
  );
}

export function formatRate(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function handoffLabel(status: HandoffStatus | null): string | null {
  if (!status) return null;
  return {
    requested: "Handoff requested",
    acknowledged: "Handoff acknowledged",
    completed: "Handoff completed",
    cancelled: "Handoff cancelled",
  }[status];
}
