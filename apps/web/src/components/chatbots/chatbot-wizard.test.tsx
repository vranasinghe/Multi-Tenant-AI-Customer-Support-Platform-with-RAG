// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import { OPTIONS, chatbot, orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({ createChatbot: vi.fn(), push: vi.fn() }));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push, replace: vi.fn() }) }));

import { ToastProvider } from "../kit/toast";
import { ChatbotWizard } from "./chatbot-wizard";

function renderWizard() {
  const user = userEvent.setup();
  render(
    <ToastProvider>
      <ChatbotWizard org={orgAs("agent")} options={OPTIONS} />
    </ToastProvider>,
  );
  return user;
}

const continueButton = () => screen.getByRole("button", { name: "Continue" });

async function walkToReview(user: ReturnType<typeof userEvent.setup>, name = "Helper") {
  await user.type(screen.getByLabelText("Name"), name);
  for (const heading of ["Behavior", "Appearance", "Model", "Review"]) {
    await user.click(continueButton());
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  }
}

describe("ChatbotWizard", () => {
  beforeEach(() => {
    mocks.createChatbot.mockReset();
    mocks.push.mockReset();
  });

  it("blocks the first step until a name is entered and focuses the invalid field", async () => {
    const user = renderWizard();

    await user.click(continueButton());

    expect(screen.getByText("Enter a name.")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveFocus();
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("heading", { name: "Basics" })).toBeInTheDocument();
  });

  it("moves focus to the step heading and marks the current step", async () => {
    const user = renderWizard();
    await user.type(screen.getByLabelText("Name"), "Helper");

    await user.click(continueButton());

    const heading = screen.getByRole("heading", { name: "Behavior" });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("button", { name: /Step 2: Behavior/ })).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(screen.getByRole("button", { name: /Step 1: Basics \(completed\)/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Step 4: Model/ })).toBeDisabled();
  });

  it("requires a language when replies are pinned to one language", async () => {
    const user = renderWizard();
    await user.type(screen.getByLabelText("Name"), "Helper");
    await user.click(continueButton());

    await user.click(screen.getByText("Always one language"));
    await user.click(continueButton());

    expect(screen.getByText("Choose a language.")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Language"), "fr");
    await user.click(continueButton());
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeInTheDocument();
  });

  it("validates brand colors on the appearance step", async () => {
    const user = renderWizard();
    await user.type(screen.getByLabelText("Name"), "Helper");
    await user.click(continueButton());
    await user.click(continueButton());

    const color = screen.getByLabelText("Brand color");
    await user.clear(color);
    await user.type(color, "purple");
    await user.click(continueButton());

    expect(screen.getByText("Use a hex color like #4F46E5.")).toBeInTheDocument();
  });

  it("creates the chatbot with the collected configuration and opens it", async () => {
    mocks.createChatbot.mockResolvedValue(chatbot({ id: "new-bot", name: "Helper" }));
    const user = renderWizard();
    await user.type(screen.getByLabelText("Name"), "  Helper ");
    await user.click(continueButton());
    await user.type(screen.getByLabelText("System instructions"), "Help with orders.");
    await user.click(screen.getByText("Friendly"));
    for (const heading of ["Appearance", "Model", "Review"]) {
      await user.click(continueButton());
      await screen.findByRole("heading", { name: heading });
    }
    await user.click(screen.getByLabelText(/Activate now/));

    await user.click(screen.getByRole("button", { name: "Create chatbot" }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/orgs/org-1/chatbots/new-bot"));
    const [orgId, body] = mocks.createChatbot.mock.calls[0]!;
    expect(orgId).toBe("org-1");
    expect(body).toMatchObject({
      name: "Helper",
      status: "active",
      instructions: "Help with orders.",
      tone: "friendly",
      model: "gpt-4.1-mini",
      language: null,
      widget_settings: { primary_color: "#4F46E5", avatar_url: null },
    });
    expect(screen.getByText("Chatbot created")).toBeInTheDocument();
  });

  it("returns to the step with a server-side field error", async () => {
    mocks.createChatbot.mockRejectedValue(
      new ApiError({
        status: 409,
        code: "chatbot_name_taken",
        message: "A chatbot with this name already exists in this organization.",
        fieldErrors: { name: "This name is already in use" },
      }),
    );
    const user = renderWizard();
    await walkToReview(user, "Taken");

    await user.click(screen.getByRole("button", { name: "Create chatbot" }));

    expect(await screen.findByRole("heading", { name: "Basics" })).toBeInTheDocument();
    expect(screen.getByText("This name is already in use")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/already exists/);
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("shows plan-limit errors without losing the form", async () => {
    mocks.createChatbot.mockRejectedValue(
      new ApiError({
        status: 402,
        code: "plan_limit_reached",
        message: "Your plan allows 25 chatbots. Delete one to create another.",
      }),
    );
    const user = renderWizard();
    await walkToReview(user);

    await user.click(screen.getByRole("button", { name: "Create chatbot" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Your plan allows 25 chatbots");
    expect(screen.getByRole("heading", { name: "Review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create chatbot" })).toBeEnabled();
  });

  it("prevents double submission while creating", async () => {
    let resolve: (value: unknown) => void = () => {};
    mocks.createChatbot.mockReturnValue(new Promise((r) => (resolve = r)));
    const user = renderWizard();
    await walkToReview(user);

    await user.click(screen.getByRole("button", { name: "Create chatbot" }));
    const pending = screen.getByRole("button", { name: "Creating…" });
    expect(pending).toBeDisabled();
    await user.click(pending);

    expect(mocks.createChatbot).toHaveBeenCalledTimes(1);
    resolve(chatbot());
  });
});
