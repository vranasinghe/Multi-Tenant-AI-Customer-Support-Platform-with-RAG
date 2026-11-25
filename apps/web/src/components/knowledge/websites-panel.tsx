"use client";

import { useRef, useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Label } from "@acs/ui/components/label";

import { TextAreaField } from "@/components/form/fields";
import { TextField, useFocusFirstInvalid } from "@/components/form/text-field";
import { ConfirmDialog } from "@/components/kit/confirm-dialog";
import { GlobeIcon, TrashIcon } from "@/components/kit/icons";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/kit/states";
import { useToast } from "@/components/kit/toast";
import { api, ApiError } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { KnowledgeSource, UploadLimits } from "@/lib/api/types";
import { SOURCE_STATUS, STAGE_LABEL, websiteSchema } from "@/lib/knowledge";
import { useAsyncData } from "@/lib/use-async-data";
import { usePolling } from "@/lib/use-polling";
import { fieldErrorsFromZod } from "@/lib/validation";
import type { FieldErrors } from "@/lib/validation";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

const num = (value: unknown): number => (typeof value === "number" ? value : 0);

function summary(source: KnowledgeSource): string {
  const documents = num(source.stats.documents);
  const failed = num(source.stats.failed);
  const parts = [`${documents} page${documents === 1 ? "" : "s"}`];
  if (failed) parts.push(`${failed} failed`);
  return parts.join(" · ");
}

export function WebsitesPanel({
  orgId,
  chatbotId,
  canWrite,
  limits,
  onChanged,
}: {
  orgId: string;
  chatbotId: string;
  canWrite: boolean;
  limits: UploadLimits | null;
  onChanged?: () => void;
}) {
  const toast = useToast();
  const formRef = useRef<HTMLFormElement>(null);
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(50);
  const [maxDepth, setMaxDepth] = useState(2);
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [deleting, setDeleting] = useState<KnowledgeSource | null>(null);
  useFocusFirstInvalid(formRef, errors);

  const { data, error, reload, update } = useAsyncData(
    () => api.listSources(orgId, chatbotId),
    [orgId, chatbotId],
  );
  const sources = data?.data.filter((s) => s.kind === "website") ?? null;
  usePolling(Boolean(sources?.some((s) => s.status === "syncing")), reload);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setFormError(null);
    const parsed = websiteSchema(limits).safeParse({
      url,
      max_pages: maxPages,
      max_depth: maxDepth,
      include,
      exclude,
      authorized,
    });
    if (!parsed.success) {
      setErrors(fieldErrorsFromZod(parsed.error));
      return;
    }
    setErrors({});
    setPending(true);
    try {
      await api.createWebsite(orgId, chatbotId, {
        url: parsed.data.url,
        max_pages: parsed.data.max_pages,
        max_depth: parsed.data.max_depth,
        include: parsed.data.include,
        exclude: parsed.data.exclude,
        confirm_authorized: true,
      });
      setUrl("");
      setAuthorized(false);
      toast.success("Website added", "Crawling started in the background.");
      reload();
      onChanged?.();
    } catch (failure) {
      if (failure instanceof ApiError && failure.fieldErrors.url) {
        setErrors({ url: failure.fieldErrors.url });
      }
      setFormError(describeApiError(failure));
    } finally {
      setPending(false);
    }
  }

  async function sync(source: KnowledgeSource) {
    try {
      const updated = await api.syncSource(orgId, chatbotId, source.id);
      update(
        (current) =>
          current && {
            ...current,
            data: current.data.map((s) => (s.id === source.id ? updated : s)),
          },
      );
    } catch (failure) {
      toast.error("Couldn't start the sync", describeApiError(failure));
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    const target = deleting;
    try {
      await api.deleteSource(orgId, chatbotId, target.id);
      update(
        (current) =>
          current && { ...current, data: current.data.filter((s) => s.id !== target.id) },
      );
      setDeleting(null);
      toast.success("Website removed", "All of its pages and passages were deleted.");
      onChanged?.();
    } catch (failure) {
      setDeleting(null);
      toast.error("Couldn't remove the website", describeApiError(failure));
    }
  }

  return (
    <div className="grid gap-6">
      {canWrite && (
        <form
          ref={formRef}
          onSubmit={onSubmit}
          noValidate
          className="grid max-w-2xl gap-4 rounded-xl border bg-card p-5"
          aria-label="Add a website"
        >
          <div className="grid gap-1">
            <h3 className="font-semibold">Add a website</h3>
            <p className="text-sm text-muted-foreground">
              Public pages on one site, starting from this address. We respect robots.txt, stay on
              the same host and never fetch private or internal addresses.
            </p>
          </div>
          {formError && <Alert variant="destructive">{formError}</Alert>}
          <TextField
            label="Starting address"
            name="url"
            type="url"
            inputMode="url"
            placeholder="https://help.example.com/"
            value={url}
            error={errors.url}
            disabled={pending}
            onChange={(event) => setUrl(event.target.value)}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Maximum pages"
              name="max_pages"
              type="number"
              min={1}
              max={limits?.max_pages_per_crawl ?? 200}
              value={Number.isNaN(maxPages) ? "" : maxPages}
              error={errors.max_pages}
              disabled={pending}
              onChange={(event) =>
                setMaxPages(event.target.value === "" ? Number.NaN : Number(event.target.value))
              }
            />
            <TextField
              label="Link depth"
              name="max_depth"
              type="number"
              min={0}
              max={5}
              value={Number.isNaN(maxDepth) ? "" : maxDepth}
              hint="0 = only the starting page."
              error={errors.max_depth}
              disabled={pending}
              onChange={(event) =>
                setMaxDepth(event.target.value === "" ? Number.NaN : Number(event.target.value))
              }
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <TextAreaField
              label="Only these paths (optional)"
              name="include"
              rows={3}
              placeholder={"/docs/*\n/help/*"}
              value={include}
              error={errors.include}
              hint="One pattern per line. * matches anything."
              disabled={pending}
              onChange={(event) => setInclude(event.target.value)}
            />
            <TextAreaField
              label="Skip these paths (optional)"
              name="exclude"
              rows={3}
              placeholder={"/blog/*\n/login"}
              value={exclude}
              error={errors.exclude}
              disabled={pending}
              onChange={(event) => setExclude(event.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-start gap-3">
              <input
                id="authorized"
                type="checkbox"
                checked={authorized}
                disabled={pending}
                aria-invalid={errors.authorized ? true : undefined}
                aria-describedby={errors.authorized ? "authorized-error" : undefined}
                onChange={(event) => setAuthorized(event.target.checked)}
                className="mt-0.5 size-4"
              />
              <Label htmlFor="authorized" className="items-start leading-snug font-normal">
                I own this website or have permission to crawl and index its content.
              </Label>
            </div>
            {errors.authorized && (
              <p id="authorized-error" className="text-sm text-destructive">
                {errors.authorized}
              </p>
            )}
          </div>
          <Button type="submit" disabled={pending} className="justify-self-start">
            {pending ? "Adding…" : "Add website"}
          </Button>
        </form>
      )}

      {error ? (
        <ErrorState title="Couldn't load websites" message={error} onRetry={reload} />
      ) : sources === null ? (
        <ListSkeleton rows={2} label="Loading websites…" />
      ) : sources.length === 0 ? (
        <EmptyState
          icon={<GlobeIcon />}
          title="No websites yet"
          description={
            canWrite
              ? "Add your help center or documentation site above."
              : "No websites have been added."
          }
        />
      ) : (
        <ul className="grid gap-3" aria-label="Websites">
          {sources.map((source) => {
            const startUrl = String(source.config.start_url ?? "");
            const busy = source.status === "syncing";
            const stage = source.job?.stage
              ? (STAGE_LABEL[source.job.stage] ?? source.job.stage)
              : null;
            return (
              <li
                key={source.id}
                className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center"
              >
                <div className="grid min-w-0 flex-1 gap-1">
                  <p className="truncate font-medium">{source.name}</p>
                  <p className="truncate text-sm text-muted-foreground">{startUrl}</p>
                  <p className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {SOURCE_STATUS[source.status]}
                    </span>
                    {busy && stage ? ` · ${stage}` : ""} · {summary(source)}
                    {source.last_synced_at && (
                      <>
                        {" "}
                        · synced{" "}
                        <time dateTime={source.last_synced_at}>
                          {dateFormat.format(new Date(source.last_synced_at))}
                        </time>
                      </>
                    )}
                  </p>
                  {source.status === "failed" && source.job?.error_code && (
                    <p className="text-sm text-destructive" role="status">
                      The last crawl failed ({source.job.error_code.replaceAll("_", " ")}).
                    </p>
                  )}
                </div>
                {canWrite && (
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => void sync(source)}
                    >
                      {busy ? "Syncing…" : "Sync now"}
                      <span className="sr-only"> {source.name}</span>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Remove ${source.name}`}
                      onClick={() => setDeleting(source)}
                    >
                      <TrashIcon />
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Remove ${deleting?.name ?? "website"}?`}
        description="Every page, passage and vector from this website is deleted immediately. You can add the site again later."
        confirmLabel="Remove website"
        destructive
        onConfirm={confirmDelete}
      />
    </div>
  );
}
