// @vitest-environment jsdom
/** AUD-06: scope changes, pagination and error handling of the inbox list. */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { ConversationList, ConversationSummary, InboxFilters } from "@/lib/api/types";
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

function row(id: string, preview: string): ConversationSummary {
  return {
    id,
    chatbot_id: "bot-1",
    chatbot_name: "Support Bot",
    channel: "widget",
    status: "open",
    preview,
    satisfaction_score: null,
    handoff_status: null,
    unanswered_count: 0,
    last_message_at: "2026-11-25T10:00:00Z",
    created_at: "2026-11-25T09:00:00Z",
  };
}

function page(rows: ConversationSummary[], next: string | null = null): ConversationList {
  return { data: rows, next_cursor: next, has_more: next !== null, total: rows.length };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const ORG_A = orgAs("admin");
const ORG_B = { ...orgAs("admin"), id: "org-2" };

const serverError = () => new ApiError({ status: 500, code: "http_error", message: "down" });

beforeEach(() => {
  mocks.listChatbots.mockReset();
  mocks.listInbox.mockReset();
  mocks.listChatbots.mockResolvedValue({ data: [{ id: "bot-1", name: "Support Bot" }] });
});

describe("inbox pagination", () => {
  it("keeps the rows already shown and appends the next page", async () => {
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) =>
      Promise.resolve(
        filters.cursor
          ? page([row("c2", "Second page question")])
          : page([row("c1", "First page question")], "cursor-1"),
      ),
    );
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await user.click(await screen.findByRole("button", { name: "Load more" }));

    expect(await screen.findByText("Second page question")).toBeInTheDocument();
    expect(screen.getByText("First page question")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(mocks.listInbox).toHaveBeenLastCalledWith(
      "org-1",
      expect.objectContaining({ cursor: "cursor-1" }),
    );
  });

  it("does not repeat a conversation that two pages both return", async () => {
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) =>
      Promise.resolve(
        filters.cursor
          ? page([row("c1", "Moved question"), row("c2", "Other question")])
          : page([row("c1", "Moved question")], "cursor-1"),
      ),
    );
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await user.click(await screen.findByRole("button", { name: "Load more" }));
    await screen.findByText("Other question");

    expect(screen.getAllByText("Moved question")).toHaveLength(1);
  });

  it("keeps the list and offers a retry when the next page fails", async () => {
    let failures = 1;
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) => {
      if (!filters.cursor) return Promise.resolve(page([row("c1", "Kept question")], "cursor-1"));
      if (failures-- > 0) return Promise.reject(serverError());
      return Promise.resolve(page([row("c2", "Later question")]));
    });
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await user.click(await screen.findByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/went wrong/i);
    expect(screen.getByText("Kept question")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Later question")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("drops a next page that arrives after the filters changed", async () => {
    const late = deferred<ConversationList>();
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) => {
      if (filters.cursor) return late.promise;
      return Promise.resolve(
        filters.status
          ? page([row("r1", "Resolved question")])
          : page([row("c1", "Open question")], "cursor-1"),
      );
    });
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await user.click(await screen.findByRole("button", { name: "Load more" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "resolved");
    await screen.findByText("Resolved question");
    await act(async () => late.resolve(page([row("c2", "Stale page question")])));

    expect(screen.queryByText("Stale page question")).not.toBeInTheDocument();
  });
});

describe("inbox scope changes", () => {
  it("removes the previous rows as soon as a filter changes, before the answer arrives", async () => {
    const pending = deferred<ConversationList>();
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) =>
      filters.status ? pending.promise : Promise.resolve(page([row("c1", "Open question")])),
    );
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await screen.findByText("Open question");
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "resolved");

    expect(screen.queryByText("Open question")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Loading conversations…");
    await act(async () => pending.resolve(page([row("r1", "Resolved question")])));
    expect(screen.getByText("Resolved question")).toBeInTheDocument();
  });

  it("removes another organization's rows immediately and ignores its late answer", async () => {
    const slowA = deferred<ConversationList>();
    const slowB = deferred<ConversationList>();
    let callsForA = 0;
    mocks.listInbox.mockImplementation((org: string) => {
      if (org === "org-2") return slowB.promise;
      callsForA += 1;
      return callsForA === 1
        ? Promise.resolve(page([row("a1", "Tenant A secret")]))
        : slowA.promise;
    });
    const user = userEvent.setup();
    const view = render(<ConversationsScreen org={ORG_A} />);
    await screen.findByText("Tenant A secret");
    await user.type(screen.getByRole("searchbox", { name: "Search conversations" }), "x");

    view.rerender(<ConversationsScreen org={ORG_B} />);

    expect(screen.queryByText("Tenant A secret")).not.toBeInTheDocument();
    await act(async () => slowA.resolve(page([row("a2", "Late tenant A row")])));
    expect(screen.queryByText("Late tenant A row")).not.toBeInTheDocument();
    await act(async () => slowB.resolve(page([row("b1", "Tenant B row")])));
    expect(screen.getByText("Tenant B row")).toBeInTheDocument();
    expect(screen.queryByText("Late tenant A row")).not.toBeInTheDocument();
  });

  it("does not carry one organization's filters or chatbot choices into another", async () => {
    mocks.listChatbots.mockImplementation((org: string) =>
      org === "org-1"
        ? Promise.resolve({ data: [{ id: "bot-a", name: "Tenant A Bot" }] })
        : new Promise(() => undefined),
    );
    mocks.listInbox.mockResolvedValue(page([row("a1", "Tenant A secret")]));
    const user = userEvent.setup();
    const view = render(<ConversationsScreen org={ORG_A} />);
    await screen.findByRole("option", { name: "Tenant A Bot" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Chatbot" }), "bot-a");

    view.rerender(<ConversationsScreen org={ORG_B} />);

    expect(screen.queryByRole("option", { name: "Tenant A Bot" })).not.toBeInTheDocument();
    await waitFor(() => expect(mocks.listInbox).toHaveBeenCalledWith("org-2", expect.anything()));
    for (const [org, filters] of mocks.listInbox.mock.calls) {
      if (org === "org-2") expect(filters).not.toHaveProperty("chatbot_id");
    }
  });

  it("ignores an error from an earlier filter after the screen has moved on", async () => {
    const slow = deferred<ConversationList>();
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) => {
      if (filters.status === "open") return slow.promise;
      return Promise.resolve(page([row("c1", `Question ${filters.status ?? "any"}`)]));
    });
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await screen.findByText("Question any");
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "open");
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "resolved");
    await screen.findByText("Question resolved");
    await act(async () => slow.reject(serverError()));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Question resolved")).toBeInTheDocument();
  });

  it("disposes quietly when unmounted before the answer arrives", async () => {
    const pending = deferred<ConversationList>();
    mocks.listInbox.mockReturnValue(pending.promise);
    const logged = vi.spyOn(console, "error");
    const view = render(<ConversationsScreen org={ORG_A} />);
    view.unmount();
    await act(async () => pending.resolve(page([row("c1", "Late question")])));

    expect(logged).not.toHaveBeenCalled();
  });
});

describe("inbox states", () => {
  it("says that nothing matches, not that nothing exists, when filters are set", async () => {
    mocks.listInbox.mockImplementation((_org: string, filters: InboxFilters) =>
      Promise.resolve(page(filters.status ? [] : [row("c1", "Open question")])),
    );
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await screen.findByText("Open question");
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "resolved");

    expect(
      await screen.findByRole("heading", { name: "No matching conversations" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("Open question")).toBeInTheDocument();
  });

  it("retries after a failure", async () => {
    mocks.listInbox
      .mockRejectedValueOnce(serverError())
      .mockResolvedValue(page([row("c1", "Recovered question")]));
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await user.click(await screen.findByRole("button", { name: /try again|retry/i }));

    expect(await screen.findByText("Recovered question")).toBeInTheDocument();
  });

  it.each([
    [401, "unauthorized", "Sign in to continue."],
    [403, "forbidden", "You don't have permission to do that."],
    [404, "not_found", "That doesn't exist, or you don't have access to it."],
  ])("shows no rows for a %s response", async (status, code, message) => {
    mocks.listInbox.mockRejectedValue(
      new ApiError({ status, code, message: "Sign in to continue." }),
    );
    render(<ConversationsScreen org={ORG_A} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByRole("list", { name: "Conversations" })).not.toBeInTheDocument();
  });

  it("filters from the start of the chosen local day", async () => {
    vi.stubEnv("TZ", "Asia/Colombo");
    mocks.listInbox.mockResolvedValue(page([row("c1", "Open question")]));
    const user = userEvent.setup();
    render(<ConversationsScreen org={ORG_A} />);
    await screen.findByText("Open question");
    await user.type(screen.getByLabelText("From date"), "2026-11-25");

    await waitFor(() =>
      expect(mocks.listInbox).toHaveBeenLastCalledWith(
        "org-1",
        // Midnight in Colombo (+05:30), not midnight UTC.
        expect.objectContaining({ from: "2026-11-24T18:30:00.000Z" }),
      ),
    );
  });
});
