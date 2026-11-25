import { publicApiBaseUrl, toApiError } from "./api/client";

export interface ChatCitation {
  id: number;
  document_id: string;
  chunk_id: string;
  title: string;
  uri: string;
  page: number | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "streaming" | "complete" | "fallback" | "interrupted" | "failed";
  citations: ChatCitation[];
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  usage_estimated: boolean;
  error_code: string | null;
  feedback: number | null;
  latency_ms?: number | null;
}

export type ChatEvent =
  | { event: "meta"; data: { conversation_id: string; message_id: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "error"; data: { code: string; message: string } }
  | { event: "done"; data: ChatMessage };

/** Bounded incremental SSE parser; handles UTF-8 and CRLF network splits. */
export async function readChatStream(response: Response, onEvent: (event: ChatEvent) => void) {
  if (!response.ok) throw await toApiError(response);
  if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("The server did not return a chat stream.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done = false;
  try {
    while (true) {
      const part = await reader.read();
      buffer += decoder.decode(part.value, { stream: !part.done });
      buffer = buffer.replace(/\r\n/g, "\n");
      if (buffer.length > 256_000) throw new Error("The chat response is too large.");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = frame.split("\n");
        const kind = lines
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim();
        const raw = lines
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (kind && raw && ["meta", "delta", "error", "done"].includes(kind)) {
          const data: unknown = JSON.parse(raw);
          if (!data || typeof data !== "object") throw new Error("Invalid chat event.");
          onEvent({ event: kind, data } as ChatEvent);
          if (kind === "done") done = true;
        }
      }
      if (part.done) break;
    }
    if (!done) throw new Error("The connection ended before the answer finished. Try again.");
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export async function sendChatMessage(
  orgId: string,
  conversationId: string,
  content: string,
  contextMessages: number,
  signal: AbortSignal,
  onEvent: (event: ChatEvent) => void,
) {
  const root = publicApiBaseUrl().replace(/\/+$/, "");
  const response = await fetch(
    `${root}/api/v1/orgs/${encodeURIComponent(orgId)}/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      credentials: "include",
      cache: "no-store",
      signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        "X-Requested-With": "platform",
      },
      body: JSON.stringify({ content, context_messages: contextMessages }),
    },
  );
  await readChatStream(response, onEvent);
}

export function safeCitationUrl(uri: string): string | undefined {
  try {
    const url = new URL(uri);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : undefined;
  } catch {
    return undefined;
  }
}
