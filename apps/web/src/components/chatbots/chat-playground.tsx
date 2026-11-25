"use client";

import { useEffect, useRef, useState } from "react";
import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";
import { Textarea } from "@acs/ui/components/textarea";

import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { Chatbot, Org } from "@/lib/api/types";
import { safeCitationUrl, sendChatMessage, type ChatMessage } from "@/lib/chat";
import { can } from "@/lib/orgs";

import { AnswerText } from "./answer-text";
import { BotAvatar } from "./widget-preview";

export function ChatPlayground({ org, bot }: { org: Org; bot: Chatbot }) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState(12);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const allowed =
    can(org, "chatbot:test") &&
    org.status === "active" &&
    !["paused", "archived"].includes(bot.status);

  useEffect(() => {
    let active = true;
    void api
      .listChatConversations(org.id, bot.id)
      .then(async ({ data }) => {
        const last = data.find((row) => row.channel === "playground");
        if (!last) return;
        const result = await api.getConversation(org.id, last.id);
        if (active) {
          setConversationId(last.id);
          setMessages(result.messages);
        }
      })
      .catch((failure: unknown) => {
        if (active) setError(describeApiError(failure));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.current?.abort();
    };
  }, [org.id, bot.id]);

  useEffect(() => {
    const pane = transcript.current;
    if (pane) pane.scrollTop = pane.scrollHeight;
  }, [messages]);

  async function send() {
    if (!allowed || busy || !question.trim()) return;
    const content = question.trim();
    setBusy(true);
    setError(null);
    const abort = new AbortController();
    controller.current = abort;
    let assistantId = "pending-answer";
    const base: ChatMessage = {
      id: "pending-question",
      role: "user",
      content,
      status: "complete",
      citations: [],
      input_tokens: 0,
      output_tokens: 0,
      estimated_cost_usd: "0",
      usage_estimated: true,
      error_code: null,
      feedback: null,
    };
    try {
      const id = conversationId ?? (await api.createConversation(org.id, bot.id)).id;
      if (abort.signal.aborted) return;
      setConversationId(id);
      setQuestion("");
      setMessages((rows) => [
        ...rows,
        base,
        { ...base, id: assistantId, role: "assistant", content: "", status: "streaming" },
      ]);
      await sendChatMessage(org.id, id, content, context, abort.signal, (part) => {
        if (part.event === "meta") {
          const previous = assistantId;
          assistantId = part.data.message_id;
          setMessages((rows) =>
            rows.map((m) => (m.id === previous ? { ...m, id: assistantId } : m)),
          );
        } else if (part.event === "delta") {
          setMessages((rows) =>
            rows.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + part.data.text } : m,
            ),
          );
        } else if (part.event === "done") {
          setMessages((rows) => rows.map((m) => (m.id === assistantId ? part.data : m)));
        } else if (part.event === "error") setError(part.data.message);
      });
    } catch (failure) {
      setMessages((rows) =>
        rows.map((m) =>
          m.id === assistantId && m.status === "streaming" ? { ...m, status: "interrupted" } : m,
        ),
      );
      if (!abort.signal.aborted) {
        setError(describeApiError(failure));
        setQuestion(content);
      }
    } finally {
      setBusy(false);
      controller.current = null;
    }
  }

  async function feedback(id: string, rating: number) {
    if (!conversationId) return;
    try {
      await api.chatFeedback(org.id, conversationId, id, rating);
      setMessages((rows) =>
        rows.map((m) => (m.id === id ? { ...m, feedback: rating || null } : m)),
      );
    } catch (failure) {
      setError(describeApiError(failure));
    }
  }

  return (
    <section className="grid max-w-4xl min-w-0 gap-5" aria-labelledby="playground-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <h2 id="playground-heading" className="font-semibold">
            Test your chatbot
          </h2>
          <p className="text-sm text-muted-foreground">
            Answers use saved settings and indexed knowledge. Test chats count toward usage.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={busy || loading}
          onClick={() => {
            setMessages([]);
            setConversationId(null);
            setError(null);
          }}
        >
          New conversation
        </Button>
      </div>
      {!allowed && <Alert>Testing is unavailable for this chatbot or your current role.</Alert>}
      {error && <Alert variant="destructive">{error}</Alert>}
      <div
        ref={transcript}
        className="grid max-h-[34rem] min-h-72 content-start gap-4 overflow-y-auto rounded-2xl border bg-muted/50 p-4 sm:p-6"
        role="log"
        aria-label="Test conversation"
        aria-live="polite"
        aria-relevant="additions text"
        tabIndex={0}
      >
        {loading ? (
          <p role="status" className="text-sm text-muted-foreground">
            Loading conversation…
          </p>
        ) : messages.length === 0 ? (
          <div className="my-auto grid justify-items-center gap-2 py-10 text-center">
            <h3 className="font-medium">Ask a question from your knowledge base</h3>
            <p className="max-w-prose text-sm text-muted-foreground">
              Try a customer question, then a follow-up. If the evidence is missing, the chatbot
              should say so.
            </p>
          </div>
        ) : (
          messages.map((m, index) => (
            <article
              key={`${m.id}-${index}`}
              className={
                m.role === "user"
                  ? "ml-auto grid max-w-[85%] gap-1 rounded-2xl rounded-br-md bg-primary px-4 py-3 text-primary-foreground"
                  : "grid max-w-[92%] gap-3 rounded-2xl rounded-bl-md border bg-card px-4 py-3.5 shadow-[var(--shadow-soft)]"
              }
            >
              <h3
                className={
                  m.role === "user"
                    ? "sr-only"
                    : "flex items-center gap-2 text-xs font-medium text-muted-foreground"
                }
              >
                {m.role === "user" ? (
                  "You"
                ) : (
                  <>
                    <BotAvatar
                      name={bot.name}
                      avatarUrl={bot.widget_settings.avatar_url}
                      color={bot.widget_settings.primary_color}
                      size="sm"
                    />
                    {bot.name}
                  </>
                )}
              </h3>
              {m.role === "assistant" && m.content ? (
                <AnswerText text={m.content} />
              ) : (
                <p className="max-w-prose text-[0.9375rem] leading-relaxed break-words whitespace-pre-wrap">
                  {m.content || (busy ? "Finding an answer…" : "No answer was received.")}
                </p>
              )}
              {m.citations.length > 0 && (
                <ul aria-label="Sources" className="flex flex-wrap gap-2 border-t pt-3 text-xs">
                  {m.citations.map((c) => (
                    <li key={c.id}>
                      {safeCitationUrl(c.uri) ? (
                        <a
                          className="inline-flex items-center rounded-md border bg-accent/60 px-2 py-1 text-accent-foreground transition-colors outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
                          href={safeCitationUrl(c.uri)}
                          target="_blank"
                          rel="noopener noreferrer nofollow"
                        >
                          [{c.id}] {c.title}
                        </a>
                      ) : (
                        <span className="inline-flex items-center rounded-md border bg-muted px-2 py-1">
                          [{c.id}] {c.title}
                        </span>
                      )}
                      {c.page !== null && <span> · page {c.page}</span>}
                    </li>
                  ))}
                </ul>
              )}
              {m.role === "assistant" && m.status !== "streaming" && (
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>
                    {m.status === "fallback"
                      ? "Insufficient evidence"
                      : m.status === "interrupted"
                        ? "Answer stopped"
                        : m.status === "failed"
                          ? "Answer failed"
                          : `${m.input_tokens + m.output_tokens} tokens${m.usage_estimated ? " (estimated)" : ""} · estimated $${Number(m.estimated_cost_usd).toFixed(6)}`}
                  </span>
                  {["complete", "fallback"].includes(m.status) && allowed && (
                    <>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label="Mark answer helpful"
                        aria-pressed={m.feedback === 1}
                        onClick={() => void feedback(m.id, m.feedback === 1 ? 0 : 1)}
                      >
                        Helpful
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        aria-label="Mark answer unhelpful"
                        aria-pressed={m.feedback === -1}
                        onClick={() => void feedback(m.id, m.feedback === -1 ? 0 : -1)}
                      >
                        Not helpful
                      </Button>
                    </>
                  )}
                </div>
              )}
            </article>
          ))
        )}
      </div>
      <div className="grid gap-3">
        <Label htmlFor="test-question">Customer question</Label>
        <Textarea
          id="test-question"
          value={question}
          maxLength={4000}
          disabled={!allowed || loading || busy}
          rows={3}
          placeholder="Ask about something in your uploaded documents…"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="chat-context">Previous messages</Label>
            <Select
              id="chat-context"
              value={context}
              disabled={busy}
              onChange={(e) => setContext(Number(e.target.value))}
            >
              <option value={0}>None</option>
              <option value={6}>Up to 6</option>
              <option value={12}>Up to 12</option>
            </Select>
          </div>
          {busy ? (
            <Button type="button" variant="outline" onClick={() => controller.current?.abort()}>
              Stop answer
            </Button>
          ) : (
            <Button
              type="button"
              disabled={!allowed || loading || !question.trim()}
              onClick={() => void send()}
            >
              Send question
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Enter to send · Shift+Enter for a new line. Verify answers before sharing them with
          customers.
        </p>
      </div>
    </section>
  );
}
