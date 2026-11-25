// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import { orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({
  listChatbots: vi.fn(),
  listInbox: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});

import { ConversationsScreen } from "./conversations-screen";

const ROW = {
  id: "conv-1",
  chatbot_id: "bot-1",
  chatbot_name: "Support Bot",
  channel: "widget" as const,
  status: "open" as const,
  preview: "Do you ship to Canada?",
  satisfaction_score: null,
  handoff_status: null,
  unanswered_count: 1,
  last_message_at: "2026-11-25T10:00:00Z",
  created_at: "2026-11-25T09:00:00Z",
};

describe("ConversationsScreen", () => {
  beforeEach(() => {
    mocks.listChatbots.mockReset();
    mocks.listInbox.mockReset();
    mocks.listChatbots.mockResolvedValue({
      data: [{ id: "bot-1", name: "Support Bot" }],
      limit: 25,
    });
    mocks.listInbox.mockResolvedValue({
      data: [ROW],
      next_cursor: null,
      has_more: false,
      total: 1,
    });
  });

  it("loads stored conversations and links to the transcript", async () => {
    render(<ConversationsScreen org={orgAs("admin")} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading conversations…");
    const list = await screen.findByRole("list", { name: "Conversations" });
    expect(list).toHaveTextContent("Do you ship to Canada?");
    expect(screen.getByRole("link", { name: /Do you ship to Canada/ })).toHaveAttribute(
      "href",
      "/orgs/org-1/conversations/conv-1",
    );
    expect(screen.getByText(/1 unanswered/)).toBeInTheDocument();
  });

  it("searches and filters through the inbox API", async () => {
    const user = userEvent.setup();
    render(<ConversationsScreen org={orgAs("viewer")} />);
    await screen.findByRole("list", { name: "Conversations" });
    await user.type(screen.getByRole("searchbox", { name: "Search conversations" }), "Canada");
    await waitFor(() => {
      expect(mocks.listInbox).toHaveBeenCalledWith(
        "org-1",
        expect.objectContaining({ q: "Canada" }),
      );
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "resolved");
    await waitFor(() => {
      expect(mocks.listInbox).toHaveBeenCalledWith(
        "org-1",
        expect.objectContaining({ status: "resolved" }),
      );
    });
  });

  it("shows an empty state when nothing is stored", async () => {
    mocks.listInbox.mockResolvedValue({ data: [], next_cursor: null, has_more: false, total: 0 });
    render(<ConversationsScreen org={orgAs("admin")} />);
    expect(
      await screen.findByRole("heading", { name: "No conversations yet" }),
    ).toBeInTheDocument();
  });

  it("shows an error when the inbox cannot load", async () => {
    mocks.listInbox.mockRejectedValue(
      new ApiError({ status: 500, code: "http_error", message: "down" }),
    );
    render(<ConversationsScreen org={orgAs("admin")} />);
    expect(await screen.findByText(/down|Something went wrong/i)).toBeInTheDocument();
  });
});
