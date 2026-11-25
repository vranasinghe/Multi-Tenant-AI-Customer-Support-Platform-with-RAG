import type { ReactNode } from "react";

import { Badge } from "@acs/ui/components/badge";
import { Button } from "@acs/ui/components/button";
import { Skeleton } from "@acs/ui/components/skeleton";
import { cn } from "@acs/ui/lib/utils";

import { AlertIcon, ClockIcon } from "./icons";

/** Page title row: heading, optional description and right-aligned actions. */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="grid min-w-0 gap-1">
        {eyebrow}
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
        {description && (
          <p className="max-w-2xl text-sm text-pretty text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** Nothing here yet: says what this place is for and offers the next step. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <div className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground [&_svg]:size-5">
          {icon}
        </div>
      )}
      <div className="grid max-w-sm gap-1">
        <h2 className="font-semibold">{title}</h2>
        <p className="text-sm text-pretty text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}

/** A load failed: what happened and a retry. Announced to screen readers. */
export function ErrorState({
  title = "Couldn't load this",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-destructive">
          <AlertIcon />
        </span>
        <div className="grid gap-1">
          <p className="font-medium">{title}</p>
          <p className="text-sm text-muted-foreground">{message}</p>
        </div>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Loading placeholder for lists and tables. */
export function ListSkeleton({ rows = 3, label = "Loading…" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="grid gap-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-4 rounded-xl border bg-card p-4">
          <Skeleton className="size-10 rounded-full" />
          <div className="grid flex-1 gap-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
          </div>
          <Skeleton className="hidden h-6 w-16 sm:block" />
        </div>
      ))}
    </div>
  );
}

export function StatSkeleton() {
  return (
    <div className="grid gap-3 rounded-xl border bg-card p-5">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-7 w-16" />
    </div>
  );
}

/**
 * Marks a feature that ships in a later phase. Placeholders must always carry this label so no
 * one mistakes illustrative UI for live data.
 */
export function ComingSoon({
  title,
  description,
  phase,
  children,
}: {
  title: string;
  description: ReactNode;
  phase: string;
  children?: ReactNode;
}) {
  return (
    <section
      aria-label={`${title} (coming soon)`}
      className="grid gap-4 rounded-xl border border-dashed bg-muted/30 p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <h2 className="font-semibold">{title}</h2>
          <p className="max-w-2xl text-sm text-pretty text-muted-foreground">{description}</p>
        </div>
        <PlaceholderBadge phase={phase} />
      </div>
      {children}
    </section>
  );
}

export function PlaceholderBadge({ phase }: { phase: string }) {
  return (
    <Badge variant="outline" className="gap-1 bg-background">
      <ClockIcon />
      Coming soon · {phase}
    </Badge>
  );
}
