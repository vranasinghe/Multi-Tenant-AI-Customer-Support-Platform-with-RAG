"use client";

import { CardIcon } from "@/components/kit/icons";
import {
  ComingSoon,
  EmptyState,
  ErrorState,
  PageHeader,
  PlaceholderBadge,
  StatSkeleton,
} from "@/components/kit/states";
import { useOrg } from "@/components/orgs/org-provider";
import { api } from "@/lib/api";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

export default function BillingPage() {
  const { org } = useOrg();
  // The chatbot allowance is real (enforced by the API today); plans and payments are not.
  const { data, error, reload } = useAsyncData(() => api.listChatbots(org.id), [org.id]);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Billing"
        description="Your plan, usage limits and invoices."
        actions={<PlaceholderBadge phase="Billing phase" />}
      />

      <section aria-labelledby="usage-heading" className="grid gap-3">
        <h2 id="usage-heading" className="font-semibold">
          Current limits
        </h2>
        {error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data ? (
          <div className="max-w-sm">
            <StatSkeleton />
          </div>
        ) : (
          <div className="grid max-w-sm gap-2 rounded-xl border bg-card p-5">
            <p className="text-sm text-muted-foreground">Chatbots</p>
            <p className="text-2xl font-semibold tabular-nums">
              {data.data.length}{" "}
              <span className="text-base text-muted-foreground">/ {data.limit}</span>
            </p>
            <div
              className="h-1.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label="Chatbots used"
              aria-valuemin={0}
              aria-valuemax={data.limit}
              aria-valuenow={data.data.length}
            >
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.min(100, (data.data.length / data.limit) * 100)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              A temporary allowance for every organization until plans launch.
            </p>
          </div>
        )}
      </section>

      <ComingSoon
        title="Plans, payments and invoices"
        phase="Billing phase"
        description={
          can(org, "billing:manage")
            ? "Choose a plan, manage your payment method and download invoices through Stripe. Message credits and usage alerts arrive with it."
            : "Only the organization owner will be able to change the plan and payment method."
        }
      >
        <EmptyState
          icon={<CardIcon />}
          title="No invoices"
          description="Invoices will be listed here once paid plans are available."
          className="bg-background"
        />
      </ComingSoon>
    </div>
  );
}
