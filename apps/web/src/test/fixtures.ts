/** Typed test fixtures for component tests (mirrors of API responses). */
import type { Chatbot, ChatbotOptions, Org, Role } from "@/lib/api/types";

const PERMISSIONS: Record<Role, string[]> = {
  owner: [
    "org:read",
    "chatbot:read",
    "chatbot:write",
    "chatbot:delete",
    "domain:manage",
    "chatbot:test",
    "conversation:read",
    "member:read",
  ],
  admin: [
    "org:read",
    "chatbot:read",
    "chatbot:write",
    "chatbot:delete",
    "domain:manage",
    "chatbot:test",
    "conversation:read",
    "member:read",
  ],
  agent: [
    "org:read",
    "chatbot:read",
    "chatbot:write",
    "chatbot:test",
    "conversation:read",
    "member:read",
  ],
  viewer: ["org:read", "chatbot:read", "conversation:read", "member:read"],
};

export function orgAs(role: Role, overrides: Partial<Org> = {}): Org {
  return {
    id: "org-1",
    name: "Acme",
    slug: "acme",
    status: "active",
    role,
    permissions: PERMISSIONS[role],
    settings: {},
    created_at: "2026-11-22T00:00:00Z",
    ...overrides,
  };
}

export const OPTIONS: ChatbotOptions = {
  models: [
    {
      id: "gpt-4.1-mini",
      label: "GPT-4.1 mini",
      provider: "openai",
      description: "Fast default",
      max_output_tokens: 4096,
      tier: "standard",
      default: true,
    },
    {
      id: "gpt-4.1-nano",
      label: "GPT-4.1 nano",
      provider: "openai",
      description: "Small",
      max_output_tokens: 2048,
      tier: "standard",
      default: false,
    },
  ],
  languages: [
    { code: "en", label: "English" },
    { code: "fr", label: "French" },
  ],
  tones: ["professional", "friendly", "concise", "custom"],
  response_lengths: ["concise", "balanced", "detailed"],
  statuses: ["draft", "active", "paused", "archived"],
  chatbot_limit: 25,
};

export function chatbot(overrides: Partial<Chatbot> = {}): Chatbot {
  return {
    id: "bot-1",
    name: "Support Bot",
    description: "Helps customers",
    status: "draft",
    public_key: "pk_live_abcdefghijklmnopqrstuvwx",
    instructions: "Be helpful.",
    tone: "professional",
    response_length: "balanced",
    welcome_message: "Hi there!",
    fallback_message: "Please contact support.",
    language_mode: "auto",
    language: null,
    model: "gpt-4.1-mini",
    temperature: 0.2,
    max_output_tokens: 600,
    strict_grounding: true,
    show_sources: true,
    retrieval_top_k: 6,
    widget_settings: {
      primary_color: "#4F46E5",
      accent_color: "#FFFFFF",
      avatar_url: null,
      position: "bottom-right",
      launcher_label: "Chat with us",
      show_branding: true,
    },
    created_by: { id: "u1", name: "Olivia" },
    created_at: "2026-11-20T10:00:00Z",
    updated_at: "2026-11-21T10:00:00Z",
    ...overrides,
  };
}
