"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { cn } from "@acs/ui/lib/utils";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { ChatbotOptions, Org } from "@/lib/api/types";
import {
  DEFAULT_FORM,
  LENGTH_OPTIONS,
  TONE_OPTIONS,
  errorsFromApi,
  toCreateBody,
  validateFields,
} from "@/lib/chatbots";
import type { ChatbotForm, FormErrors } from "@/lib/chatbots";

import { CheckIcon } from "../kit/icons";
import { useToast } from "../kit/toast";
import {
  AppearanceFields,
  BasicsFields,
  BehaviorFields,
  LanguageFields,
  ModelFields,
} from "./config-fields";
import type { FieldsProps } from "./config-fields";
import { WidgetPreview } from "./widget-preview";

export const WIZARD_STEPS = [
  {
    id: "basics",
    title: "Basics",
    description: "Name your assistant and write its greeting.",
    fields: ["name", "description", "welcome_message"],
  },
  {
    id: "behavior",
    title: "Behavior",
    description: "Tell it what to do, how to sound and which language to use.",
    fields: [
      "instructions",
      "tone",
      "response_length",
      "fallback_message",
      "language_mode",
      "language",
    ],
  },
  {
    id: "appearance",
    title: "Appearance",
    description: "Match the chat widget to your brand.",
    fields: ["widget_settings"],
  },
  {
    id: "model",
    title: "Model",
    description: "Choose the AI model and how it generates answers.",
    fields: ["model", "temperature", "max_output_tokens", "retrieval_top_k"],
  },
  {
    id: "review",
    title: "Review",
    description: "Check everything, then create your chatbot.",
    fields: [],
  },
] as const;

function stepOf(field: string): number {
  const index = WIZARD_STEPS.findIndex((step) =>
    step.fields.some((f) => field === f || field.startsWith(`${f}.`)),
  );
  return index === -1 ? 0 : index;
}

export function ChatbotWizard({ org, options }: { org: Org; options: ChatbotOptions }) {
  const router = useRouter();
  const toast = useToast();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const defaultModel = options.models.find((m) => m.default)?.id ?? DEFAULT_FORM.model;
  const [form, setForm] = useState<ChatbotForm>({ ...DEFAULT_FORM, model: defaultModel });
  const [step, setStep] = useState(0);
  const [visited, setVisited] = useState(0);
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [activate, setActivate] = useState(false);
  const [pending, setPending] = useState(false);
  // Where to move focus after the next render (step change or failed validation).
  const focusTarget = useRef<"heading" | "invalid" | null>(null);

  const current = WIZARD_STEPS[step]!;
  const isLast = step === WIZARD_STEPS.length - 1;

  useEffect(() => {
    if (focusTarget.current === "heading") headingRef.current?.focus();
    if (focusTarget.current === "invalid") {
      formRef.current?.querySelector<HTMLElement>("[aria-invalid='true']")?.focus();
    }
    focusTarget.current = null;
  });

  const fieldProps: FieldsProps = {
    form,
    errors,
    options,
    disabled: pending,
    onChange: (patch) => setForm((value) => ({ ...value, ...patch })),
    onWidgetChange: (patch) =>
      setForm((value) => ({ ...value, widget_settings: { ...value.widget_settings, ...patch } })),
  };

  function goTo(index: number) {
    setStep(index);
    setVisited((value) => Math.max(value, index));
    setFormError(null);
    focusTarget.current = "heading";
  }

  function next() {
    const stepErrors = validateFields(form, options.models, current.fields);
    setErrors(stepErrors);
    if (Object.keys(stepErrors).length > 0) {
      focusTarget.current = "invalid";
      return;
    }
    goTo(step + 1);
  }

  async function create() {
    const allErrors = validateFields(form, options.models);
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors);
      goTo(stepOf(Object.keys(allErrors)[0]!));
      return;
    }
    setPending(true);
    setFormError(null);
    try {
      const bot = await api.createChatbot(
        org.id,
        toCreateBody(form, activate ? "active" : "draft"),
      );
      toast.success("Chatbot created", `${bot.name} is ready to configure.`);
      router.push(`/orgs/${encodeURIComponent(org.id)}/chatbots/${encodeURIComponent(bot.id)}`);
    } catch (error) {
      setPending(false);
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length > 0) {
        const apiErrors = errorsFromApi(error.fieldErrors);
        setErrors(apiErrors);
        goTo(stepOf(Object.keys(apiErrors)[0]!));
        setFormError(describeApiError(error));
        return;
      }
      setFormError(describeApiError(error));
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    if (isLast) void create();
    else next();
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[13rem_1fr]">
      <nav aria-label="Setup steps">
        <ol className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1">
          {WIZARD_STEPS.map((item, index) => {
            const done = index < step;
            const reachable = index <= visited && !pending;
            return (
              <li key={item.id} className="shrink-0">
                <button
                  type="button"
                  disabled={!reachable}
                  aria-current={index === step ? "step" : undefined}
                  aria-label={`Step ${index + 1}: ${item.title}${done ? " (completed)" : ""}`}
                  onClick={() => goTo(index)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-default",
                    index === step ? "bg-accent font-medium" : "text-muted-foreground",
                    reachable && index !== step && "hover:bg-accent/60 hover:text-foreground",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs",
                      index === step && "border-foreground",
                      done && "border-transparent bg-primary text-primary-foreground",
                    )}
                  >
                    {done ? <CheckIcon width={12} height={12} /> : index + 1}
                  </span>
                  <span>{item.title}</span>
                </button>
              </li>
            );
          })}
        </ol>
      </nav>

      <form ref={formRef} onSubmit={onSubmit} noValidate className="grid min-w-0 gap-6">
        <div className="grid gap-1">
          <p className="text-sm text-muted-foreground">
            Step {step + 1} of {WIZARD_STEPS.length}
          </p>
          <h2 ref={headingRef} tabIndex={-1} className="text-xl font-semibold outline-none">
            {current.title}
          </h2>
          <p className="text-sm text-muted-foreground">{current.description}</p>
        </div>

        {formError && <Alert variant="destructive">{formError}</Alert>}

        {current.id === "basics" && <BasicsFields {...fieldProps} />}
        {current.id === "behavior" && (
          <div className="grid gap-8">
            <BehaviorFields {...fieldProps} />
            <LanguageFields {...fieldProps} />
          </div>
        )}
        {current.id === "appearance" && (
          <div className="grid gap-8 xl:grid-cols-[1fr_18rem]">
            <AppearanceFields {...fieldProps} />
            <WidgetPreview form={form} />
          </div>
        )}
        {current.id === "model" && <ModelFields {...fieldProps} />}
        {current.id === "review" && (
          <ReviewStep form={form} options={options} activate={activate} onActivate={setActivate} />
        )}

        <div className="flex flex-col-reverse gap-2 border-t pt-6 sm:flex-row sm:justify-between">
          {step === 0 ? (
            <Button asChild variant="ghost">
              <Link href={`/orgs/${encodeURIComponent(org.id)}/chatbots`}>Cancel</Link>
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => goTo(step - 1)}
            >
              Back
            </Button>
          )}
          <Button type="submit" disabled={pending}>
            {isLast ? (pending ? "Creating…" : "Create chatbot") : "Continue"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function ReviewStep({
  form,
  options,
  activate,
  onActivate,
}: {
  form: ChatbotForm;
  options: ChatbotOptions;
  activate: boolean;
  onActivate: (value: boolean) => void;
}) {
  const model = options.models.find((m) => m.id === form.model);
  const language =
    form.language_mode === "auto"
      ? "Matches the visitor"
      : (options.languages.find((l) => l.code === form.language)?.label ?? "—");
  const rows: [string, string][] = [
    ["Name", form.name.trim()],
    ["Welcome message", form.welcome_message.trim() || "—"],
    [
      "Instructions",
      form.instructions.trim() ? `${form.instructions.trim().length} characters` : "None yet",
    ],
    ["Tone", TONE_OPTIONS.find((t) => t.value === form.tone)?.label ?? form.tone],
    ["Response length", LENGTH_OPTIONS.find((l) => l.value === form.response_length)?.label ?? ""],
    ["Language", language],
    ["Answers only from knowledge", form.strict_grounding ? "Yes" : "No"],
    ["Model", model?.label ?? form.model],
    ["Temperature", String(form.temperature)],
  ];
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_18rem]">
      <div className="grid gap-6">
        <dl className="divide-y rounded-xl border bg-card">
          {rows.map(([label, value]) => (
            <div key={label} className="grid gap-1 px-4 py-3 sm:grid-cols-[12rem_1fr]">
              <dt className="text-sm text-muted-foreground">{label}</dt>
              <dd className="text-sm break-words">{value}</dd>
            </div>
          ))}
        </dl>
        <fieldset className="grid gap-2">
          <legend className="mb-1.5 text-sm font-medium">Status after creation</legend>
          <label className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm has-[:checked]:border-foreground">
            <input
              type="radio"
              name="initial_status"
              className="mt-0.5"
              checked={!activate}
              onChange={() => onActivate(false)}
            />
            <span className="grid gap-0.5">
              <span className="font-medium">Save as draft</span>
              <span className="text-muted-foreground">
                Recommended. Add knowledge first, then activate.
              </span>
            </span>
          </label>
          <label className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm has-[:checked]:border-foreground">
            <input
              type="radio"
              name="initial_status"
              className="mt-0.5"
              checked={activate}
              onChange={() => onActivate(true)}
            />
            <span className="grid gap-0.5">
              <span className="font-medium">Activate now</span>
              <span className="text-muted-foreground">Mark it live as soon as it is created.</span>
            </span>
          </label>
        </fieldset>
      </div>
      <WidgetPreview form={form} />
    </div>
  );
}
