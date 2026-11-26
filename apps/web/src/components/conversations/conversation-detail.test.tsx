// @vitest-environment jsdom
/** AUD-06: the persisted transcript, its older pages and its scope changes. */
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { ConversationDetail, InboxMessage, MessagePage } from "@/lib/api/types";
import { orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({
  getConversationDetail: vi.fn(),
  listMessages: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { ConversationDetailScreen } from "./conversation-detail";
import { formatWhen } from "./conversation-status";

function message(id: string, content: string, extra: Partial<InboxMessage> = {}): InboxMessage {
  return {
    id,
    role: "user",
    content,
    status: "complete",
    citations: [],
    input_tokens: 0,
    output_tokens: 0,
    estimated_cost_usd: "0",
    usage_estimated: false,
    error_code: null,
    feedback: null,
    created_at: "2026-11-25T10:00:00Z",
    ...extra,
  };
}

function detail(
  id: string,
  messages: InboxMessage[],
  older: string | null = null,
): ConversationDetail {
  return {
    id,
    chatbot_id: "bot-1",
    chatbot_name: "Support Bot",
    channel: "widget",
    status: "open",
    preview: `Preview of ${id}`,
    satisfaction_score: null,
    satisfaction_comment: null,
    handoff_status: null,
    handoff_reason: null,
    handoff_contact: null,
    created_at: "2026-11-25T09:00:00Z",
    last_message_at: "2026-11-25T10:00:00Z",
    messages,
    older_cursor: older,
    events: [],
  };
}

const older = (data: InboxMessage[], next: string | null = null): MessagePage => ({
  data,
  next_cursor: next,
  has_more: next !== null,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}

const ORG = orgAs("viewer");
const history = () => screen.getByRole("list", { name: "Message history" });
const shown = () =>
  within(history())
    .getAllByTestId("message-content")
    .map((node) => node.textContent);

beforeEach(() => {
  mocks.getConversationDetail.mockReset();
  mocks.listMessages.mockReset();
});

describe("ConversationDetailScreen", () => {
  it("shows each message's own time and state", async () => {
    mocks.getConversationDetail.mockResolvedValue(
      detail("conv-1", [
        message("m1", "Where is my order?", { created_at: "2026-11-25T10:00:00Z" }),
        message("m2", "Partial answer", {
          role: "assistant",
          status: "interrupted",
          created_at: "2026-11-25T10:00:07Z",
          feedback: -1,
        }),
        message("m3", "", {
          role: "assistant",
          status: "failed",
          created_at: "2026-11-26T08:15:00Z",
        }),
      ]),
    );
    render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    await screen.findByRole("list", { name: "Message history" });

    const items = within(history()).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent(formatWhen("2026-11-25T10:00:00Z"));
    expect(items[1]).toHaveTextContent(/interrupted/i);
    expect(items[1]).toHaveTextContent("not helpful");
    expect(items[2]).toHaveTextContent(/failed/i);
    expect(items[2]).toHaveTextContent(formatWhen("2026-11-26T08:15:00Z"));
    expect(history().querySelector("time")).toHaveAttribute("datetime", "2026-11-25T10:00:00Z");
  });

  it("loads earlier messages above the newest ones until none are left", async () => {
    mocks.getConversationDetail.mockResolvedValue(
      detail("conv-1", [message("m5", "five"), message("m6", "six")], "c-1"),
    );
    mocks.listMessages.mockImplementation((_org: string, _id: string, cursor: string) =>
      Promise.resolve(
        cursor === "c-1"
          ? older([message("m3", "three"), message("m4", "four")], "c-2")
          : older([message("m1", "one"), message("m2", "two")]),
      ),
    );
    const user = userEvent.setup();
    render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    await user.click(await screen.findByRole("button", { name: "Load earlier messages" }));
    await screen.findByText("three");
    await user.click(screen.getByRole("button", { name: "Load earlier messages" }));
    await screen.findByText("one");

    expect(shown()).toEqual(["one", "two", "three", "four", "five", "six"]);
    expect(screen.queryByRole("button", { name: "Load earlier messages" })).not.toBeInTheDocument();
    expect(mocks.listMessages).toHaveBeenNthCalledWith(1, "org-1", "conv-1", "c-1");
  });

  it("offers no earlier messages when the transcript is complete", async () => {
    mocks.getConversationDetail.mockResolvedValue(detail("conv-1", [message("m1", "only")]));
    render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    await screen.findByText("only");

    expect(screen.queryByRole("button", { name: "Load earlier messages" })).not.toBeInTheDocument();
  });

  it("keeps the transcript and retries when earlier messages fail to load", async () => {
    mocks.getConversationDetail.mockResolvedValue(
      detail("conv-1", [message("m2", "newest")], "c-1"),
    );
    mocks.listMessages
      .mockRejectedValueOnce(new ApiError({ status: 500, code: "http_error", message: "down" }))
      .mockResolvedValue(older([message("m1", "earliest")]));
    const user = userEvent.setup();
    render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    await user.click(await screen.findByRole("button", { name: "Load earlier messages" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/went wrong/i);
    expect(screen.getByText("newest")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Load earlier messages" }));
    expect(await screen.findByText("earliest")).toBeInTheDocument();
  });

  it.each([
    ["another conversation", ORG, "conv-2"],
    ["another organization", { ...ORG, id: "org-2" }, "conv-1"],
  ])("clears the transcript at once when switching to %s", async (_label, org, id) => {
    const next = deferred<ConversationDetail>();
    const late = deferred<MessagePage>();
    mocks.getConversationDetail
      .mockResolvedValueOnce(detail("conv-1", [message("m2", "private words")], "c-1"))
      .mockReturnValue(next.promise);
    mocks.listMessages.mockReturnValue(late.promise);
    const user = userEvent.setup();
    const view = render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    await user.click(await screen.findByRole("button", { name: "Load earlier messages" }));

    view.rerender(<ConversationDetailScreen org={org} conversationId={id} />);

    expect(screen.queryByText("private words")).not.toBeInTheDocument();
    expect(screen.queryByText("Preview of conv-1")).not.toBeInTheDocument();
    await act(async () => late.resolve(older([message("m1", "late private words")])));
    expect(screen.queryByText("late private words")).not.toBeInTheDocument();
    await act(async () => next.resolve(detail(id, [message("n1", "new words")])));
    expect(screen.getByText("new words")).toBeInTheDocument();
    expect(screen.queryByText("late private words")).not.toBeInTheDocument();
  });

  it("renders stored citations and hostile text as inert text", async () => {
    const hostile = '<img src=x onerror="window.pwned=1">';
    mocks.getConversationDetail.mockResolvedValue(
      detail("conv-1", [
        message("m1", hostile),
        message("m2", `Answer [1] ${hostile}`, {
          role: "assistant",
          citations: [
            {
              id: 1,
              document_id: "doc-1",
              chunk_id: "chunk-1",
              title: `Returns ${hostile}`,
              uri: "javascript:alert(1)",
              page: 3,
            },
          ],
        }),
      ]),
    );
    render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    await screen.findByRole("list", { name: "Message history" });

    const sources = screen.getByRole("list", { name: "Sources" });
    expect(sources).toHaveTextContent(`[1] Returns ${hostile} · page 3`);
    expect(within(sources).queryByRole("link")).not.toBeInTheDocument();
    expect(history().querySelector("img")).toBeNull();
    expect(history().textContent).not.toContain("javascript:alert(1)");
  });

  it("offers a retry when the conversation cannot be loaded", async () => {
    mocks.getConversationDetail
      .mockRejectedValueOnce(new ApiError({ status: 404, code: "not_found", message: "no" }))
      .mockResolvedValue(detail("conv-1", [message("m1", "back again")]));
    const user = userEvent.setup();
    render(<ConversationDetailScreen org={ORG} conversationId="conv-1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("you don't have access");
    await user.click(screen.getByRole("button", { name: /try again|retry/i }));

    expect(await screen.findByText("back again")).toBeInTheDocument();
  });
});
