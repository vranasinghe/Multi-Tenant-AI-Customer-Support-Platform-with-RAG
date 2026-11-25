// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import type { ChatEvent, ChatMessage } from "@/lib/chat";
import type * as ChatModule from "@/lib/chat";
import { chatbot, orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({
  listChatConversations: vi.fn(),
  getConversation: vi.fn(),
  createConversation: vi.fn(),
  chatFeedback: vi.fn(),
  sendChatMessage: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: mocks }));
vi.mock("@/lib/chat", async (original) => ({
  ...(await original<typeof ChatModule>()),
  sendChatMessage: mocks.sendChatMessage,
}));
import { ChatPlayground } from "./chat-playground";

const answer: ChatMessage = {
  id: "answer-1",
  role: "assistant",
  content: "Returns within thirty days [1]",
  status: "complete",
  citations: [
    {
      id: 1,
      document_id: "doc-1",
      chunk_id: "chunk-1",
      title: "Returns policy",
      uri: "https://help.test/returns",
      page: 1,
    },
  ],
  input_tokens: 100,
  output_tokens: 10,
  estimated_cost_usd: ".000056",
  usage_estimated: false,
  error_code: null,
  feedback: null,
};

beforeEach(() => {
  Object.values(mocks).forEach((mock) => mock.mockReset());
  mocks.listChatConversations.mockResolvedValue({ data: [] });
  mocks.createConversation.mockResolvedValue({ id: "conversation-1" });
  mocks.chatFeedback.mockResolvedValue({ status: "ok" });
  mocks.sendChatMessage.mockImplementation(
    async (_org, _id, _question, _context, _signal, emit: (e: ChatEvent) => void) => {
      emit({ event: "meta", data: { conversation_id: "conversation-1", message_id: answer.id } });
      emit({ event: "delta", data: { text: "Returns within " } });
      emit({ event: "done", data: answer });
    },
  );
});

it("sends a question, displays citations and usage, and saves feedback", async () => {
  const user = userEvent.setup();
  render(<ChatPlayground org={orgAs("admin")} bot={chatbot()} />);
  await waitFor(() => expect(screen.getByLabelText("Customer question")).toBeEnabled());
  await user.type(screen.getByLabelText("Customer question"), "Returns policy?");
  await user.click(screen.getByRole("button", { name: "Send question" }));
  expect(await screen.findByText(/Returns within thirty days/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "[1] Returns policy" })).toHaveAttribute(
    "href",
    "https://help.test/returns",
  );
  expect(screen.getByText(/110 tokens/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Mark answer helpful" }));
  expect(mocks.chatFeedback).toHaveBeenCalledWith("org-1", "conversation-1", "answer-1", 1);
  await user.click(screen.getByRole("button", { name: "New conversation" }));
  expect(screen.getByText("Ask a question from your knowledge base")).toBeInTheDocument();
});

it("restores the last playground conversation", async () => {
  mocks.listChatConversations.mockResolvedValue({ data: [{ id: "saved", channel: "playground" }] });
  mocks.getConversation.mockResolvedValue({ messages: [answer] });
  render(<ChatPlayground org={orgAs("admin")} bot={chatbot()} />);
  expect(await screen.findByText(/Returns within thirty days/)).toBeInTheDocument();
  expect(mocks.getConversation).toHaveBeenCalledWith("org-1", "saved");
});

it("stops an active request and marks partial text interrupted", async () => {
  mocks.sendChatMessage.mockImplementation(
    (_org, _id, _q, _c, signal: AbortSignal, emit: (e: ChatEvent) => void) =>
      new Promise<void>((_resolve, reject) => {
        emit({
          event: "meta",
          data: { conversation_id: "conversation-1", message_id: "answer-1" },
        });
        emit({ event: "delta", data: { text: "Partial answer" } });
        signal.addEventListener("abort", () => reject(new DOMException("Stopped", "AbortError")));
      }),
  );
  const user = userEvent.setup();
  render(<ChatPlayground org={orgAs("admin")} bot={chatbot()} />);
  await waitFor(() => expect(screen.getByLabelText("Customer question")).toBeEnabled());
  await user.type(screen.getByLabelText("Customer question"), "Returns?");
  await user.click(screen.getByRole("button", { name: "Send question" }));
  await user.click(await screen.findByRole("button", { name: "Stop answer" }));
  expect(await screen.findByText("Answer stopped")).toBeInTheDocument();
  expect(screen.getByText("Partial answer")).toBeInTheDocument();
});

it("disables generation for a viewer", async () => {
  render(<ChatPlayground org={orgAs("viewer")} bot={chatbot()} />);
  expect(await screen.findByText(/Testing is unavailable/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
});
