/**
 * Chatbot form model shared by the creation wizard and the settings editor.
 *
 * Validation here is UX only and mirrors the API (services/api/app/schemas/chatbots.py); the
 * server re-validates everything, including catalog rules such as per-model token limits.
 */
import { z } from "zod";

import type {
  Chatbot,
  ChatbotConfig,
  ChatbotStatus,
  ChatbotTone,
  CreateChatbotBody,
  ModelOption,
  ResponseLength,
  UpdateChatbotBody,
  WidgetSettings,
} from "@/lib/api/types";

export const LIMITS = {
  name: 80,
  description: 500,
  instructions: 4000,
  message: 500,
  launcherLabel: 40,
  minTokens: 64,
  maxTokens: 4096,
  minTopK: 1,
  maxTopK: 12,
} as const;

/** Form state: strings where inputs produce strings ("" = not set). */
export interface ChatbotForm extends Omit<ChatbotConfig, "language" | "widget_settings"> {
  language: string;
  widget_settings: Omit<WidgetSettings, "avatar_url"> & { avatar_url: string };
}

export type FormErrors = Record<string, string>;

export const DEFAULT_FORM: ChatbotForm = {
  name: "",
  description: "",
  instructions: "",
  tone: "professional",
  response_length: "balanced",
  welcome_message: "Hi! How can I help you today?",
  fallback_message: "I'm not sure about that. Could you rephrase, or contact our support team?",
  language_mode: "auto",
  language: "",
  model: "gpt-4.1-mini",
  temperature: 0.2,
  max_output_tokens: 600,
  strict_grounding: true,
  show_sources: true,
  retrieval_top_k: 6,
  widget_settings: {
    primary_color: "#4F46E5",
    accent_color: "#FFFFFF",
    avatar_url: "",
    position: "bottom-right",
    launcher_label: "Chat with us",
    show_branding: true,
  },
};

export const TONE_OPTIONS: readonly { value: ChatbotTone; label: string; description: string }[] = [
  { value: "professional", label: "Professional", description: "Clear, courteous, businesslike." },
  { value: "friendly", label: "Friendly", description: "Warm and conversational." },
  { value: "concise", label: "Concise", description: "Short, direct answers." },
  { value: "custom", label: "Custom", description: "Follow the tone in your instructions." },
];

export const LENGTH_OPTIONS: readonly {
  value: ResponseLength;
  label: string;
  description: string;
}[] = [
  { value: "concise", label: "Concise", description: "One or two sentences." },
  { value: "balanced", label: "Balanced", description: "A short paragraph." },
  { value: "detailed", label: "Detailed", description: "Step-by-step when useful." },
];

export const STATUS_META: Record<ChatbotStatus, { label: string; description: string }> = {
  draft: { label: "Draft", description: "Being set up. Not answering visitors." },
  active: { label: "Active", description: "Live on every connected channel." },
  paused: { label: "Paused", description: "Temporarily not answering visitors." },
  archived: { label: "Archived", description: "Retired. Kept for reference." },
};

const HEX = /^#[0-9A-Fa-f]{6}$/;
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;

const text = (max: number, label: string) =>
  z
    .string()
    .max(max, `${label} must be at most ${max} characters.`)
    .refine((value) => !CONTROL.test(value), `${label} contains characters that aren't allowed.`);

export function chatbotFormSchema(models: readonly ModelOption[]) {
  return z
    .object({
      name: text(LIMITS.name, "Name").refine((v) => v.trim().length > 0, "Enter a name."),
      description: text(LIMITS.description, "Description"),
      instructions: text(LIMITS.instructions, "Instructions"),
      tone: z.enum(["professional", "friendly", "concise", "custom"]),
      response_length: z.enum(["concise", "balanced", "detailed"]),
      welcome_message: text(LIMITS.message, "Welcome message"),
      fallback_message: text(LIMITS.message, "Fallback message"),
      language_mode: z.enum(["auto", "fixed"]),
      language: z.string(),
      model: z.string().min(1, "Choose a model."),
      temperature: z
        .number({ error: "Enter a number between 0 and 1." })
        .min(0, "Use a value between 0 and 1.")
        .max(1, "Use a value between 0 and 1."),
      max_output_tokens: z
        .number({ error: "Enter a whole number." })
        .int("Enter a whole number.")
        .min(LIMITS.minTokens, `Use at least ${LIMITS.minTokens} tokens.`)
        .max(LIMITS.maxTokens, `Use at most ${LIMITS.maxTokens} tokens.`),
      strict_grounding: z.boolean(),
      show_sources: z.boolean(),
      retrieval_top_k: z
        .number({ error: "Enter a whole number." })
        .int("Enter a whole number.")
        .min(LIMITS.minTopK, `Use ${LIMITS.minTopK}–${LIMITS.maxTopK}.`)
        .max(LIMITS.maxTopK, `Use ${LIMITS.minTopK}–${LIMITS.maxTopK}.`),
      widget_settings: z.object({
        primary_color: z.string().regex(HEX, "Use a hex color like #4F46E5."),
        accent_color: z.string().regex(HEX, "Use a hex color like #FFFFFF."),
        avatar_url: z
          .string()
          .trim()
          .max(2048, "That URL is too long.")
          .refine(
            (v) => v === "" || (/^https:\/\/\S+$/i.test(v) && URL.canParse(v)),
            "Use an https:// image URL, or leave it empty.",
          ),
        position: z.enum(["bottom-right", "bottom-left"]),
        launcher_label: text(LIMITS.launcherLabel, "Launcher label"),
        show_branding: z.boolean(),
      }),
    })
    .superRefine((value, ctx) => {
      if (value.language_mode === "fixed" && !value.language) {
        ctx.addIssue({ code: "custom", path: ["language"], message: "Choose a language." });
      }
      const model = models.find((m) => m.id === value.model);
      if (models.length > 0 && !model) {
        ctx.addIssue({ code: "custom", path: ["model"], message: "Choose an available model." });
      }
      if (model && value.max_output_tokens > model.max_output_tokens) {
        ctx.addIssue({
          code: "custom",
          path: ["max_output_tokens"],
          message: `${model.label} supports at most ${model.max_output_tokens} tokens.`,
        });
      }
    });
}

/** Errors keyed by dotted path ("name", "widget_settings.primary_color"); first message wins. */
export function errorsFromZod(error: z.ZodError): FormErrors {
  const result: FormErrors = {};
  for (const issue of error.issues) {
    const key = issue.path.map(String).join(".") || "form";
    if (!(key in result)) result[key] = issue.message;
  }
  return result;
}

/** Validate only the given fields (wizard steps). Prefix match covers nested groups. */
export function validateFields(
  form: ChatbotForm,
  models: readonly ModelOption[],
  fields?: readonly string[],
): FormErrors {
  const parsed = chatbotFormSchema(models).safeParse(form);
  if (parsed.success) return {};
  const all = errorsFromZod(parsed.error);
  if (!fields) return all;
  return Object.fromEntries(
    Object.entries(all).filter(([key]) =>
      fields.some((field) => key === field || key.startsWith(`${field}.`)),
    ),
  );
}

export function formFromChatbot(bot: Chatbot): ChatbotForm {
  return {
    name: bot.name,
    description: bot.description,
    instructions: bot.instructions,
    tone: bot.tone,
    response_length: bot.response_length,
    welcome_message: bot.welcome_message,
    fallback_message: bot.fallback_message,
    language_mode: bot.language_mode,
    language: bot.language ?? "",
    model: bot.model,
    temperature: bot.temperature,
    max_output_tokens: bot.max_output_tokens,
    strict_grounding: bot.strict_grounding,
    show_sources: bot.show_sources,
    retrieval_top_k: bot.retrieval_top_k,
    widget_settings: { ...bot.widget_settings, avatar_url: bot.widget_settings.avatar_url ?? "" },
  };
}

function normalized(form: ChatbotForm): ChatbotConfig {
  return {
    ...form,
    name: form.name.trim(),
    description: form.description.trim(),
    instructions: form.instructions.trim(),
    welcome_message: form.welcome_message.trim(),
    fallback_message: form.fallback_message.trim(),
    language: form.language_mode === "fixed" && form.language ? form.language : null,
    temperature: Math.round(form.temperature * 100) / 100,
    widget_settings: {
      ...form.widget_settings,
      primary_color: form.widget_settings.primary_color.toUpperCase(),
      accent_color: form.widget_settings.accent_color.toUpperCase(),
      launcher_label: form.widget_settings.launcher_label.trim(),
      avatar_url: form.widget_settings.avatar_url.trim() || null,
    },
  };
}

export function toCreateBody(form: ChatbotForm, status: "draft" | "active"): CreateChatbotBody {
  return { ...normalized(form), status };
}

/** Merge-patch body with only what changed, so concurrent edits to other fields survive. */
export function diffForUpdate(original: Chatbot, form: ChatbotForm): UpdateChatbotBody {
  const next = normalized(form);
  const body: Record<string, unknown> = {};
  for (const key of Object.keys(next) as (keyof ChatbotConfig)[]) {
    if (key === "widget_settings") continue;
    if (next[key] !== original[key]) body[key] = next[key];
  }
  const widget: Partial<WidgetSettings> = {};
  for (const key of Object.keys(next.widget_settings) as (keyof WidgetSettings)[]) {
    if (next.widget_settings[key] !== original.widget_settings[key]) {
      Object.assign(widget, { [key]: next.widget_settings[key] });
    }
  }
  if (Object.keys(widget).length > 0) body.widget_settings = widget;
  return body as UpdateChatbotBody;
}

/** Field errors from a 422 response, keyed the same way as client-side errors. */
export function errorsFromApi(fieldErrors: Record<string, string>): FormErrors {
  return Object.fromEntries(
    Object.entries(fieldErrors).map(([field, message]) => [field.replace(/^body\./, ""), message]),
  );
}

/** Readable text color (black/white) on a hex background, for previews. */
export function contrastText(hex: string): "#000000" | "#FFFFFF" {
  if (!HEX.test(hex)) return "#FFFFFF";
  const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const luminance = 0.2126 * lin(r!) + 0.7152 * lin(g!) + 0.0722 * lin(b!);
  return luminance > 0.4 ? "#000000" : "#FFFFFF";
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").toUpperCase() + (parts[1]?.[0] ?? "").toUpperCase();
}
