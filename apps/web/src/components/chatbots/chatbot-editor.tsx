"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";
import { Skeleton } from "@acs/ui/components/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@acs/ui/components/tabs";

import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { Chatbot, ChatbotOptions, ChatbotStatus, Org } from "@/lib/api/types";
import {
  STATUS_META,
  diffForUpdate,
  errorsFromApi,
  formFromChatbot,
  validateFields,
} from "@/lib/chatbots";
import type { ChatbotForm, FormErrors } from "@/lib/chatbots";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

import { ConfirmDialog } from "../kit/confirm-dialog";
import { ArrowLeftIcon } from "../kit/icons";
import { ErrorState } from "../kit/states";
import { useToast } from "../kit/toast";
import {
  AppearanceFields,
  BasicsFields,
  BehaviorFields,
  LanguageFields,
  ModelFields,
} from "./config-fields";
import type { FieldsProps } from "./config-fields";
import { StatusBadge } from "./status-badge";
import { BotAvatar, WidgetPreview } from "./widget-preview";
import { WidgetInstall } from "./widget-install";
import { ChatPlayground } from "./chat-playground";

const TABS = [
  {
    id: "general",
    label: "General",
    fields: ["name", "description", "welcome_message", "language_mode", "language"],
  },
  {
    id: "behavior",
    label: "Behavior",
    fields: [
      "instructions",
      "tone",
      "response_length",
      "fallback_message",
      "strict_grounding",
      "show_sources",
    ],
  },
  { id: "appearance", label: "Appearance", fields: ["widget_settings"] },
  {
    id: "model",
    label: "Model",
    fields: ["model", "temperature", "max_output_tokens", "retrieval_top_k"],
  },
  { id: "install", label: "Install", fields: [] },
  { id: "playground", label: "Test chat", fields: [] },
] as const;
type TabId = (typeof TABS)[number]["id"] | "danger";

function tabOf(field: string): TabId {
  return (
    TABS.find((tab) => tab.fields.some((f) => field === f || field.startsWith(`${f}.`)))?.id ??
    "general"
  );
}

export function ChatbotEditorPage({ org, chatbotId }: { org: Org; chatbotId: string }) {
  const { data, error, reload } = useAsyncData(
    () => Promise.all([api.getChatbot(org.id, chatbotId), api.chatbotOptions(org.id)]),
    [org.id, chatbotId],
  );

  if (error) {
    return (
      <div className="grid gap-4">
        <BackLink orgId={org.id} />
        <ErrorState title="Couldn't load this chatbot" message={error} onRetry={reload} />
      </div>
    );
  }
  if (!data) return <EditorSkeleton />;
  const [bot, options] = data;
  return <ChatbotEditor key={bot.id} org={org} initial={bot} options={options} />;
}

function BackLink({ orgId }: { orgId: string }) {
  return (
    <Link
      href={`/orgs/${encodeURIComponent(orgId)}/chatbots`}
      className="inline-flex w-fit items-center gap-1.5 rounded-sm text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      <ArrowLeftIcon />
      All chatbots
    </Link>
  );
}

function EditorSkeleton() {
  return (
    <div role="status" className="grid gap-6">
      <span className="sr-only">Loading chatbot…</span>
      <Skeleton className="h-4 w-24" />
      <div className="flex items-center gap-4">
        <Skeleton className="size-12 rounded-full" />
        <div className="grid gap-2">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
      </div>
      <Skeleton className="h-9 w-full" />
      <div className="grid gap-4">
        <Skeleton className="h-9 w-full max-w-md" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}

export function ChatbotEditor({
  org,
  initial,
  options,
}: {
  org: Org;
  initial: Chatbot;
  options: ChatbotOptions;
}) {
  const router = useRouter();
  const toast = useToast();
  const formRef = useRef<HTMLFormElement>(null);
  const canWrite = can(org, "chatbot:write") && org.status === "active";
  const canDelete = can(org, "chatbot:delete") && org.status === "active";

  const [saved, setSaved] = useState<Chatbot>(initial);
  const [form, setForm] = useState<ChatbotForm>(() => formFromChatbot(initial));
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("general");
  const [saving, setSaving] = useState(false);
  const [statusPending, setStatusPending] = useState(false);
  const [confirm, setConfirm] = useState<"rotate" | "delete" | null>(null);
  const focusInvalid = useRef(false);

  const changes = useMemo(() => diffForUpdate(saved, form), [saved, form]);
  const dirty = Object.keys(changes).length > 0;

  useEffect(() => {
    if (!focusInvalid.current) return;
    focusInvalid.current = false;
    formRef.current?.querySelector<HTMLElement>("[aria-invalid='true']")?.focus();
  });

  // Warn before a reload or tab close throws away unsaved edits.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const fieldProps: FieldsProps = {
    form,
    errors,
    options,
    disabled: !canWrite || saving,
    onChange: (patch) => setForm((value) => ({ ...value, ...patch })),
    onWidgetChange: (patch) =>
      setForm((value) => ({ ...value, widget_settings: { ...value.widget_settings, ...patch } })),
  };

  function showErrors(next: FormErrors) {
    setErrors(next);
    const first = Object.keys(next)[0];
    if (first) {
      setTab(tabOf(first));
      focusInvalid.current = true;
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!dirty || saving || !canWrite) return;
    setFormError(null);
    const clientErrors = validateFields(form, options.models);
    if (Object.keys(clientErrors).length > 0) {
      showErrors(clientErrors);
      return;
    }
    setSaving(true);
    try {
      const updated = await api.updateChatbot(org.id, saved.id, changes);
      setSaved(updated);
      setForm(formFromChatbot(updated));
      setErrors({});
      toast.success("Changes saved");
    } catch (failure) {
      if (failure instanceof ApiError && Object.keys(failure.fieldErrors).length > 0) {
        showErrors(errorsFromApi(failure.fieldErrors));
      }
      setFormError(describeApiError(failure));
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(status: ChatbotStatus) {
    if (status === saved.status) return;
    setStatusPending(true);
    try {
      const updated = await api.updateChatbot(org.id, saved.id, { status });
      setSaved(updated);
      toast.success(`Status changed to ${STATUS_META[status].label.toLowerCase()}`);
    } catch (failure) {
      toast.error("Couldn't change status", describeApiError(failure));
    } finally {
      setStatusPending(false);
    }
  }

  async function rotateKey() {
    try {
      const updated = await api.rotateChatbotKey(org.id, saved.id);
      setSaved(updated);
      setConfirm(null);
      toast.success("Public key rotated", "Update the snippet on your website.");
    } catch (failure) {
      setConfirm(null);
      toast.error("Couldn't rotate key", describeApiError(failure));
    }
  }

  async function deleteBot() {
    try {
      await api.deleteChatbot(org.id, saved.id);
      toast.success("Chatbot deleted", `${saved.name} was removed.`);
      router.replace(`/orgs/${encodeURIComponent(org.id)}/chatbots`);
    } catch (failure) {
      setConfirm(null);
      toast.error("Couldn't delete chatbot", describeApiError(failure));
    }
  }

  return (
    <div className="grid min-w-0 gap-6 pb-24">
      <BackLink orgId={org.id} />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          <BotAvatar
            name={saved.name}
            avatarUrl={saved.widget_settings.avatar_url}
            color={saved.widget_settings.primary_color}
          />
          <div className="grid min-w-0 gap-1">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{saved.name}</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <StatusBadge status={saved.status} />
              <span>{STATUS_META[saved.status].description}</span>
            </div>
          </div>
        </div>
        {canWrite && (
          <div className="grid gap-1.5 sm:w-44">
            <Label htmlFor="chatbot-status">Status</Label>
            <Select
              id="chatbot-status"
              value={saved.status}
              disabled={statusPending}
              onChange={(event) => void changeStatus(event.target.value as ChatbotStatus)}
            >
              {options.statuses.map((status) => (
                <option key={status} value={status}>
                  {STATUS_META[status].label}
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>

      {!canWrite && (
        <Alert>
          {org.status !== "active"
            ? "This organization is read-only, so settings can't be changed."
            : "You have view-only access. Ask an admin or agent to make changes."}
        </Alert>
      )}

      <form ref={formRef} onSubmit={save} noValidate className="min-w-0">
        <Tabs className="min-w-0" value={tab} onValueChange={(value) => setTab(value as TabId)}>
          <TabsList aria-label="Chatbot settings">
            {TABS.map((item) => {
              const hasError = Object.keys(errors).some((key) => tabOf(key) === item.id);
              return (
                <TabsTrigger key={item.id} value={item.id}>
                  {item.label}
                  {hasError && (
                    <span
                      className="size-1.5 rounded-full bg-destructive"
                      aria-label="has errors"
                    />
                  )}
                </TabsTrigger>
              );
            })}
            {canDelete && <TabsTrigger value="danger">Danger zone</TabsTrigger>}
          </TabsList>

          {formError && <Alert variant="destructive">{formError}</Alert>}

          <TabsContent value="general" className="grid max-w-2xl gap-8">
            <BasicsFields {...fieldProps} />
            <LanguageFields {...fieldProps} />
          </TabsContent>
          <TabsContent value="behavior" className="max-w-2xl">
            <BehaviorFields {...fieldProps} />
          </TabsContent>
          <TabsContent value="appearance" className="grid gap-8 xl:grid-cols-[1fr_20rem]">
            <AppearanceFields {...fieldProps} />
            <WidgetPreview form={form} />
          </TabsContent>
          <TabsContent value="model" className="max-w-3xl">
            <ModelFields {...fieldProps} />
          </TabsContent>
          <TabsContent value="playground" className="min-w-0">
            <ChatPlayground org={org} bot={saved} />
          </TabsContent>
          <TabsContent value="install" className="min-w-0">
            <WidgetInstall org={org} bot={saved} onRotate={() => setConfirm("rotate")} />
          </TabsContent>
          {canDelete && (
            <TabsContent value="danger" className="max-w-2xl">
              <section
                className="grid gap-3 rounded-xl border border-destructive/40 p-5"
                aria-labelledby="delete-heading"
              >
                <h2 id="delete-heading" className="font-semibold">
                  Delete this chatbot
                </h2>
                <p className="text-sm text-muted-foreground">
                  It stops answering immediately and disappears from your workspace. Its public key
                  stops working.
                </p>
                <Button
                  type="button"
                  variant="destructive"
                  className="justify-self-start"
                  onClick={() => setConfirm("delete")}
                >
                  Delete chatbot
                </Button>
              </section>
            </TabsContent>
          )}
        </Tabs>

        {canWrite && tab !== "playground" && tab !== "install" && (
          <div
            className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 backdrop-blur lg:left-64"
            role="region"
            aria-label="Save changes"
          >
            <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
              <p className="text-sm text-muted-foreground" aria-live="polite">
                {dirty ? "You have unsaved changes." : "All changes saved."}
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  disabled={!dirty || saving}
                  onClick={() => {
                    setForm(formFromChatbot(saved));
                    setErrors({});
                    setFormError(null);
                  }}
                >
                  Discard
                </Button>
                <Button type="submit" disabled={!dirty || saving}>
                  {saving ? "Saving…" : "Save changes"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </form>

      <ConfirmDialog
        open={confirm === "rotate"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title="Rotate the public key?"
        description="The current key stops working immediately. Any website using it will lose the chat widget until you update the snippet."
        confirmLabel="Rotate key"
        onConfirm={rotateKey}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={`Delete ${saved.name}?`}
        description="This chatbot stops answering immediately and is removed from your workspace."
        confirmLabel="Delete chatbot"
        confirmText={saved.name}
        destructive
        onConfirm={deleteBot}
      />
    </div>
  );
}
