// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiClientModule from "@/lib/api/client";
import { orgAs } from "@/test/fixtures";

const mocks = vi.hoisted(() => ({
  listChatbots: vi.fn(),
  analyticsSummary: vi.fn(),
  analyticsTimeseries: vi.fn(),
  listKnowledgeGaps: vi.fn(),
  createConversationExport: vi.fn(),
  downloadConversationExport: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});

import { AnalyticsDashboard } from "./analytics-dashboard";

const SUMMARY = {
  from: "2026-10-26T00:00:00Z",
  to: "2026-11-25T00:00:00Z",
  chatbot_id: null,
  channel: null,
  conversations: 4,
  messages_user: 10,
  messages_assistant: 10,
  resolved: 2,
  unresolved: 1,
  handed_off: 1,
  open: 0,
  resolution_rate: 0.5,
  csat_submitted: 2,
  csat_positive: 2,
  satisfaction_rate: 1,
  grounded_answers: 8,
  ungrounded_answers: 2,
  grounded_rate: 0.8,
  feedback_up: 3,
  feedback_down: 1,
  thumbs_up_ratio: 0.75,
  unanswered: 2,
  unanswered_rate: 0.2,
  prompt_tokens: 100,
  completion_tokens: 50,
  charged_tokens: 150,
  estimated_cost_usd: "0.0123",
  cost_is_estimate: true,
  latency_p95_ms: 800,
  chatbots: [
    {
      chatbot_id: "bot-1",
      chatbot_name: "Support Bot",
      conversations: 4,
      resolution_rate: 0.5,
      satisfaction_rate: 1,
      grounded_rate: 0.8,
      unanswered: 2,
      charged_tokens: 150,
      estimated_cost_usd: "0.0123",
    },
  ],
  definitions: {
    resolution_rate: "resolved / closed",
    satisfaction_rate: "CSAT 4-5",
    grounded_rate: "cited replies",
    playground: "excluded",
  },
};

describe("AnalyticsDashboard", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((fn) => fn.mockReset());
    mocks.listChatbots.mockResolvedValue({
      data: [{ id: "bot-1", name: "Support Bot" }],
      limit: 25,
    });
    mocks.analyticsSummary.mockResolvedValue(SUMMARY);
    mocks.analyticsTimeseries.mockResolvedValue({
      metric: "conversations",
      interval: "day",
      from: SUMMARY.from,
      to: SUMMARY.to,
      points: [{ t: "2026-11-25T00:00:00Z", value: 4 }],
    });
    mocks.listKnowledgeGaps.mockResolvedValue({
      data: [
        {
          cluster_key: "canada ship",
          representative: "Do you ship to Canada?",
          count: 3,
          chatbot_id: "bot-1",
          chatbot_name: "Support Bot",
          last_asked_at: "2026-11-25T00:00:00Z",
          reasons: { insufficient_evidence: 3 },
        },
      ],
    });
  });

  it("renders live rates and never invents resolution from AI answers", async () => {
    render(<AnalyticsDashboard org={orgAs("admin")} />);
    expect(await screen.findByRole("heading", { name: "Analytics" })).toBeInTheDocument();
    expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("100%").length).toBeGreaterThan(0);
    expect(screen.getByText(/resolved \/ closed/i)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Daily conversations" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Knowledge gaps" })).toHaveTextContent("Canada");
  });

  it("exports CSV for admins", async () => {
    const user = userEvent.setup();
    mocks.createConversationExport.mockResolvedValue({
      id: "exp-1",
      status: "ready",
      row_count: 4,
      created_at: SUMMARY.from,
      expires_at: SUMMARY.to,
      download_path: "/orgs/org-1/exports/exp-1/download",
    });
    mocks.downloadConversationExport.mockResolvedValue(new Blob(["id\nconv-1"]));
    const click = vi.fn();
    const originalClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = click;
    URL.createObjectURL = vi.fn(() => "blob:test");
    URL.revokeObjectURL = vi.fn();
    try {
      render(<AnalyticsDashboard org={orgAs("admin")} />);
      await screen.findByRole("heading", { name: "Analytics" });
      await user.click(screen.getByRole("button", { name: "Export CSV" }));
      await waitFor(() =>
        expect(mocks.createConversationExport).toHaveBeenCalledWith("org-1", expect.any(Object)),
      );
      expect(mocks.downloadConversationExport).toHaveBeenCalledWith("org-1", "exp-1");
    } finally {
      HTMLAnchorElement.prototype.click = originalClick;
    }
  });

  it("hides export from viewers", async () => {
    render(<AnalyticsDashboard org={orgAs("viewer")} />);
    await screen.findByRole("heading", { name: "Analytics" });
    expect(screen.queryByRole("button", { name: "Export CSV" })).not.toBeInTheDocument();
  });
});
