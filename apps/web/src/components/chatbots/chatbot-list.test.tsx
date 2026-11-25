// @vitest-environment jsdom
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { chatbot, orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({ listChatbots: vi.fn(), deleteChatbot: vi.fn() }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});

import { ToastProvider } from "../kit/toast";
import { ChatbotList } from "./chatbot-list";

const BOTS = [
  chatbot({ id: "b1", name: "Support Bot", status: "active" }),
  chatbot({ id: "b2", name: "Sales Bot", status: "draft", description: "" }),
];

function renderList(role: Role = "admin") {
  const user = userEvent.setup();
  render(
    <ToastProvider>
      <ChatbotList org={orgAs(role)} />
    </ToastProvider>,
  );
  return user;
}

describe("ChatbotList", () => {
  beforeEach(() => {
    mocks.listChatbots.mockReset();
    mocks.deleteChatbot.mockReset();
    mocks.listChatbots.mockResolvedValue({ data: BOTS, limit: 25 });
  });

  it("shows a loading skeleton, then the chatbots with status and usage", async () => {
    renderList();

    expect(screen.getByRole("status")).toHaveTextContent("Loading chatbots…");
    const list = await screen.findByRole("list", { name: "Chatbots" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByText("Active")).toBeInTheDocument();
    expect(within(items[1]!).getByText("No description")).toBeInTheDocument();
    expect(screen.getByText("2 of 25 chatbots used")).toBeInTheDocument();
  });

  it("shows an empty state with a create action", async () => {
    mocks.listChatbots.mockResolvedValue({ data: [], limit: 25 });
    renderList("agent");

    expect(await screen.findByRole("heading", { name: "No chatbots yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create chatbot" })).toHaveAttribute(
      "href",
      "/orgs/org-1/chatbots/new",
    );
  });

  it("hides create and delete controls from viewers", async () => {
    renderList("viewer");

    await screen.findByRole("list", { name: "Chatbots" });
    expect(screen.queryByRole("link", { name: /New chatbot/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^View/ })).toHaveLength(2);
  });

  it("agents can edit but not delete", async () => {
    renderList("agent");

    await screen.findByRole("list", { name: "Chatbots" });
    expect(screen.getByRole("link", { name: /New chatbot/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });

  it("shows an error state and retries", async () => {
    mocks.listChatbots
      .mockRejectedValueOnce(new ApiError({ status: 500, code: "internal_error", message: "x" }))
      .mockResolvedValueOnce({ data: BOTS, limit: 25 });
    const user = renderList();

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load chatbots");
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("list", { name: "Chatbots" })).toBeInTheDocument();
  });

  it("filters by status and search text through the API", async () => {
    const user = renderList();
    await screen.findByRole("list", { name: "Chatbots" });

    await user.selectOptions(screen.getByLabelText("Filter by status"), "paused");
    await user.type(screen.getByLabelText("Search chatbots"), "sup");

    await waitFor(() =>
      expect(mocks.listChatbots).toHaveBeenLastCalledWith("org-1", { status: "paused", q: "sup" }),
    );
  });

  it("deletes only after confirmation and announces the result", async () => {
    mocks.deleteChatbot.mockResolvedValue(undefined);
    const user = renderList();
    await screen.findByRole("list", { name: "Chatbots" });

    await user.click(screen.getByRole("button", { name: "Delete Sales Bot" }));
    const dialog = screen.getByRole("alertdialog", { name: "Delete Sales Bot?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mocks.deleteChatbot).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete Sales Bot" }));
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete chatbot" }),
    );

    await waitFor(() => expect(mocks.deleteChatbot).toHaveBeenCalledWith("org-1", "b2"));
    expect(await screen.findByText("Chatbot deleted")).toBeInTheDocument();
    expect(screen.queryByText("Sales Bot")).not.toBeInTheDocument();
  });

  it("disables creation at the plan limit", async () => {
    mocks.listChatbots.mockResolvedValue({ data: BOTS, limit: 2 });
    renderList();

    expect(await screen.findByText(/reached your plan's chatbot limit/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New chatbot/ })).toBeDisabled();
  });
});
