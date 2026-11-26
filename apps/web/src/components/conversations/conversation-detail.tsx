"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@acs/ui/components/button";
import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";
import { Textarea } from "@acs/ui/components/textarea";

import { AnswerText } from "@/components/chatbots/answer-text";
import { ArrowLeftIcon } from "@/components/kit/icons";
import { ConfirmDialog } from "@/components/kit/confirm-dialog";
import { ErrorState, ListSkeleton, PageHeader } from "@/components/kit/states";
import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { InboxMessage, MessagePage, Org } from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

import { ConversationStatusBadge, formatWhen, handoffLabel } from "./conversation-status";

export function ConversationDetailScreen(props: { org: Org; conversationId: string }) {
  // Keyed by scope: nothing of the previous conversation or organization stays on screen.
  return <Detail key={`${props.org.id}/${props.conversationId}`} {...props} />;
}

function Detail({ org, conversationId }: { org: Org; conversationId: string }) {
  const router = useRouter();
  const base = `/orgs/${encodeURIComponent(org.id)}`;
  const { data, error, reload, update } = useAsyncData(
    () => api.getConversationDetail(org.id, conversationId),
    [org.id, conversationId],
  );
  const writable = can(org, "conversation:write");
  const deletable = can(org, "conversation:delete");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [contact, setContact] = useState("");
  const [score, setScore] = useState("5");
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      update(await api.getConversationDetail(org.id, conversationId));
    } catch (failure) {
      setMessage(describeApiError(failure));
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return <ListSkeleton label="Loading conversation…" rows={6} />;

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow={
          <Link
            href={`${base}/conversations`}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            <ArrowLeftIcon /> All conversations
          </Link>
        }
        title={<span className="wrap-anywhere">{data.preview || "Conversation"}</span>}
        description={`${data.chatbot_name} · ${data.channel} · last message ${formatWhen(data.last_message_at)}`}
        actions={<ConversationStatusBadge status={data.status} />}
      />

      {message && (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}

      <section
        aria-labelledby="outcome-heading"
        className="grid gap-3 rounded-xl border bg-card p-5"
      >
        <h2 id="outcome-heading" className="font-semibold">
          Outcome
        </h2>
        <p className="text-sm text-muted-foreground">
          Resolution is an explicit staff decision. A completed AI reply is not treated as resolved.
        </p>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Satisfaction</dt>
            <dd>{data.satisfaction_score ? `${data.satisfaction_score} / 5` : "Not submitted"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Handoff</dt>
            <dd>{handoffLabel(data.handoff_status) ?? "None"}</dd>
          </div>
        </dl>
        {writable && (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void run(() => api.updateConversationStatus(org.id, data.id, "resolved"))
              }
            >
              Mark resolved
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() =>
                void run(() => api.updateConversationStatus(org.id, data.id, "unresolved"))
              }
            >
              Mark unresolved
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => void run(() => api.updateConversationStatus(org.id, data.id, "open"))}
            >
              Reopen
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => void run(() => api.markUnanswered(org.id, data.id))}
            >
              Mark latest question unanswered
            </Button>
          </div>
        )}
      </section>

      {writable && (
        <section
          aria-labelledby="handoff-heading"
          className="grid gap-3 rounded-xl border bg-card p-5"
        >
          <h2 id="handoff-heading" className="font-semibold">
            Human handoff
          </h2>
          {data.handoff_reason && (
            <p className="text-sm text-pretty">
              {data.handoff_reason}
              {data.handoff_contact ? ` · ${data.handoff_contact}` : ""}
            </p>
          )}
          {!data.handoff_status && (
            <form
              className="grid gap-3 sm:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (!reason.trim()) return;
                void run(() =>
                  api.requestHandoff(org.id, data.id, reason.trim(), contact.trim() || undefined),
                );
              }}
            >
              <div className="grid gap-1 sm:col-span-2">
                <Label htmlFor="handoff-reason">Why a human should take this</Label>
                <Textarea
                  id="handoff-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  maxLength={500}
                  required
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="handoff-contact">Customer contact (optional)</Label>
                <input
                  id="handoff-contact"
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                  value={contact}
                  onChange={(event) => setContact(event.target.value)}
                  maxLength={200}
                />
              </div>
              <Button type="submit" disabled={busy} className="self-end justify-self-start">
                Request handoff
              </Button>
            </form>
          )}
          {data.handoff_status === "requested" && (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => void run(() => api.updateHandoff(org.id, data.id, "acknowledged"))}
              >
                Acknowledge
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => void run(() => api.updateHandoff(org.id, data.id, "completed"))}
              >
                Complete handoff
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => void run(() => api.updateHandoff(org.id, data.id, "cancelled"))}
              >
                Cancel
              </Button>
            </div>
          )}
        </section>
      )}

      {writable && (
        <section
          aria-labelledby="csat-heading"
          className="grid gap-3 rounded-xl border bg-card p-5"
        >
          <h2 id="csat-heading" className="font-semibold">
            Record customer satisfaction
          </h2>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void run(() => api.recordSatisfaction(org.id, data.id, Number(score)));
            }}
          >
            <div className="grid gap-1">
              <Label htmlFor="csat">Score</Label>
              <Select id="csat" value={score} onChange={(event) => setScore(event.target.value)}>
                <option value="1">1 — very dissatisfied</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="4">4</option>
                <option value="5">5 — very satisfied</option>
              </Select>
            </div>
            <Button type="submit" disabled={busy}>
              Save CSAT
            </Button>
          </form>
        </section>
      )}

      <section aria-labelledby="history-heading" className="grid gap-3">
        <h2 id="history-heading" className="font-semibold">
          Messages
        </h2>
        <History
          orgId={org.id}
          conversationId={conversationId}
          latest={data.messages}
          olderCursor={data.older_cursor}
        />
      </section>

      {deletable && (
        <>
          <Button
            type="button"
            variant="destructive"
            className="justify-self-start"
            onClick={() => setConfirmDelete(true)}
          >
            Delete conversation
          </Button>
          <ConfirmDialog
            open={confirmDelete}
            onOpenChange={setConfirmDelete}
            title="Delete this conversation?"
            description="Messages and feedback are removed. Daily analytics totals are kept without the transcript."
            confirmLabel="Delete"
            destructive
            onConfirm={async () => {
              await api.deleteConversation(org.id, data.id);
              router.push(`${base}/conversations`);
            }}
          />
        </>
      )}
    </div>
  );
}

/** The newest messages come with the conversation; earlier ones are fetched page by page. */
function History({
  orgId,
  conversationId,
  latest,
  olderCursor,
}: {
  orgId: string;
  conversationId: string;
  latest: InboxMessage[];
  olderCursor: string | null;
}) {
  const [pages, setPages] = useState<MessagePage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const oldest = pages[pages.length - 1];
  const cursor = oldest ? oldest.next_cursor : olderCursor;

  // Oldest first. Ids are kept once, whatever the pages overlap.
  const messages = new Map<string, InboxMessage>();
  for (const page of [...pages].reverse()) {
    for (const item of page.data) messages.set(item.id, item);
  }
  for (const item of latest) messages.set(item.id, item);

  async function loadEarlier(from: string) {
    setLoading(true);
    setError(null);
    try {
      const page = await api.listMessages(orgId, conversationId, from);
      setPages((current) => [...current, page]);
    } catch (failure) {
      setError(describeApiError(failure));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-3">
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {cursor && (
        <Button
          type="button"
          variant="outline"
          className="justify-self-start"
          disabled={loading}
          onClick={() => void loadEarlier(cursor)}
        >
          Load earlier messages
        </Button>
      )}
      {messages.size === 0 ? (
        <p className="text-sm text-muted-foreground">
          No messages are stored for this conversation.
        </p>
      ) : (
        <ol className="grid gap-3" aria-label="Message history">
          {[...messages.values()].map((item) => (
            <MessageItem key={item.id} item={item} />
          ))}
        </ol>
      )}
    </div>
  );
}

function MessageItem({ item }: { item: InboxMessage }) {
  return (
    <li className="min-w-0 rounded-xl border bg-card p-4 wrap-anywhere">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {item.role === "user" ? "Customer" : "Assistant"} · {item.status} ·{" "}
        <time dateTime={item.created_at}>{formatWhen(item.created_at)}</time>
      </p>
      <div data-testid="message-content">
        {item.role === "assistant" ? (
          <AnswerText text={item.content} />
        ) : (
          <p className="mt-2 text-sm text-pretty whitespace-pre-wrap">{item.content}</p>
        )}
      </div>
      {item.citations.length > 0 && (
        // Stored snapshots of what the answer cited. Text only: no link to the document.
        <ul aria-label="Sources" className="mt-2 grid gap-1 text-xs text-muted-foreground">
          {item.citations.map((citation) => (
            <li key={`${item.id}-${citation.id}`}>
              [{citation.id}] {citation.title}
              {citation.page ? ` · page ${citation.page}` : ""}
            </li>
          ))}
        </ul>
      )}
      {item.feedback != null && item.feedback !== 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          Answer feedback: {item.feedback === 1 ? "helpful" : "not helpful"}
        </p>
      )}
    </li>
  );
}
