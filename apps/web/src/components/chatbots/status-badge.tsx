import { cn } from "@acs/ui/lib/utils";

import type { ChatbotStatus } from "@/lib/api/types";
import { STATUS_META } from "@/lib/chatbots";

const DOT: Record<ChatbotStatus, string> = {
  draft: "bg-muted-foreground/60",
  active: "bg-success",
  paused: "bg-amber-500",
  archived: "bg-muted-foreground/30",
};

/** Status with a colored dot *and* a text label, so color is never the only signal. */
export function StatusBadge({ status }: { status: ChatbotStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium">
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", DOT[status])} />
      {STATUS_META[status].label}
    </span>
  );
}
