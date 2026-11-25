// @vitest-environment jsdom
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type { Org, Role } from "@/lib/api/types";
import { OPTIONS, chatbot, orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({
  updateChatbot: vi.fn(),
  deleteChatbot: vi.fn(),
  rotateChatbotKey: vi.fn(),
  getChatbot: vi.fn(),
  chatbotOptions: vi.fn(),
  replace: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: mocks.replace }),
}));

import { ToastProvider } from "../kit/toast";
import { ChatbotEditor, ChatbotEditorPage } from "./chatbot-editor";

function renderEditor(org: Org = orgAs("admin")) {
  const user = userEvent.setup();
  render(
    <ToastProvider>
      <ChatbotEditor org={org} initial={chatbot()} options={OPTIONS} />
    </ToastProvider>,
  );
  return user;
}

const save = () => screen.getByRole("button", { name: "Save changes" });

describe("ChatbotEditor", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it("enables saving only after a change and sends just the changed fields", async () => {
    mocks.updateChatbot.mockImplementation(async (_org, _id, body) => chatbot(body));
    const user = renderEditor();
    expect(save()).toBeDisabled();
    expect(screen.getByText("All changes saved.")).toBeInTheDocument();

    const name = screen.getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Renamed Bot");
    expect(screen.getByText("You have unsaved changes.")).toBeInTheDocument();
    await user.click(save());

    await waitFor(() =>
      expect(mocks.updateChatbot).toHaveBeenCalledWith("org-1", "bot-1", { name: "Renamed Bot" }),
    );
    expect(await screen.findByText("Changes saved")).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  it("sends nested appearance changes as a partial widget patch", async () => {
    mocks.updateChatbot.mockResolvedValue(chatbot());
    const user = renderEditor();

    await user.click(screen.getByRole("tab", { name: "Appearance" }));
    const label = screen.getByLabelText("Launcher label");
    await user.clear(label);
    await user.type(label, "Ask us");
    await user.click(save());

    await waitFor(() =>
      expect(mocks.updateChatbot).toHaveBeenCalledWith("org-1", "bot-1", {
        widget_settings: { launcher_label: "Ask us" },
      }),
    );
  });

  it("switches to the tab with the first invalid field instead of saving", async () => {
    const user = renderEditor();

    await user.click(screen.getByRole("tab", { name: "Model" }));
    const temperature = screen.getByLabelText("Temperature");
    await user.clear(temperature);
    await user.type(temperature, "3");
    await user.click(screen.getByRole("tab", { name: "General" }));
    await user.click(save());

    expect(screen.getByRole("tab", { name: /Model/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Use a value between 0 and 1.")).toBeInTheDocument();
    expect(mocks.updateChatbot).not.toHaveBeenCalled();
  });

  it("shows server validation errors next to the field", async () => {
    mocks.updateChatbot.mockRejectedValue(
      new ApiError({
        status: 409,
        code: "chatbot_name_taken",
        message: "A chatbot with this name already exists in this organization.",
        fieldErrors: { name: "This name is already in use" },
      }),
    );
    const user = renderEditor();

    await user.type(screen.getByLabelText("Name"), " 2");
    await user.click(save());

    expect(await screen.findByText("This name is already in use")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
  });

  it("discards unsaved edits", async () => {
    const user = renderEditor();
    await user.type(screen.getByLabelText("Name"), " draft");

    await user.click(screen.getByRole("button", { name: "Discard" }));

    expect(screen.getByLabelText("Name")).toHaveValue("Support Bot");
    expect(save()).toBeDisabled();
  });

  it("changes status immediately", async () => {
    mocks.updateChatbot.mockResolvedValue(chatbot({ status: "active" }));
    const user = renderEditor();

    await user.selectOptions(screen.getByLabelText("Status"), "active");

    await waitFor(() =>
      expect(mocks.updateChatbot).toHaveBeenCalledWith("org-1", "bot-1", { status: "active" }),
    );
    expect(await screen.findByText("Status changed to active")).toBeInTheDocument();
  });

  it("requires typing the chatbot name before deleting", async () => {
    mocks.deleteChatbot.mockResolvedValue(undefined);
    const user = renderEditor();

    await user.click(screen.getByRole("tab", { name: "Danger zone" }));
    await user.click(screen.getByRole("button", { name: "Delete chatbot" }));
    const dialog = screen.getByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Delete chatbot" });
    expect(confirm).toBeDisabled();

    await user.type(within(dialog).getByLabelText(/Type Support Bot to confirm/), "Support Bot");
    await user.click(confirm);

    await waitFor(() => expect(mocks.deleteChatbot).toHaveBeenCalledWith("org-1", "bot-1"));
    expect(mocks.replace).toHaveBeenCalledWith("/orgs/org-1/chatbots");
  });

  it("confirms before rotating the public key", async () => {
    mocks.rotateChatbotKey.mockResolvedValue(
      chatbot({ public_key: "pk_live_zyxwvutsrqponmlkjihgfedc" }),
    );
    const user = renderEditor();

    await user.click(screen.getByRole("tab", { name: "Install" }));
    await user.click(screen.getByRole("button", { name: "Rotate" }));
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Rotate key" }),
    );

    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Public key" })).toHaveValue(
        "pk_live_zyxwvutsrqponmlkjihgfedc",
      ),
    );
  });

  it.each<[Role, Partial<Org>]>([
    ["viewer", {}],
    ["admin", { status: "restricted" }],
  ])("is read-only for %s (%o)", (role, overrides) => {
    renderEditor(orgAs(role, overrides));

    expect(screen.getByLabelText("Name")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Danger zone" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/view-only|read-only/);
  });
});

describe("ChatbotEditorPage", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it("shows a skeleton, then the editor", async () => {
    mocks.getChatbot.mockResolvedValue(chatbot());
    mocks.chatbotOptions.mockResolvedValue(OPTIONS);
    render(
      <ToastProvider>
        <ChatbotEditorPage org={orgAs("admin")} chatbotId="bot-1" />
      </ToastProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Loading chatbot…");
    expect(await screen.findByRole("heading", { name: "Support Bot" })).toBeInTheDocument();
  });

  it("shows a not-found error for a chatbot outside the organization", async () => {
    mocks.getChatbot.mockRejectedValue(
      new ApiError({ status: 404, code: "not_found", message: "Not Found" }),
    );
    mocks.chatbotOptions.mockResolvedValue(OPTIONS);
    render(
      <ToastProvider>
        <ChatbotEditorPage org={orgAs("admin")} chatbotId="foreign" />
      </ToastProvider>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That doesn't exist, or you don't have access to it.",
    );
  });
});
