/**
 * Knowledge helpers. Client-side checks are UX only: the API validates the extension, declared
 * type and file *signature*, enforces size/quota limits, and is the authority.
 */
import { z } from "zod";

import type {
  DocumentStatus,
  KnowledgeDocument,
  SourceStatus,
  UploadLimits,
} from "@/lib/api/types";

export const DEFAULT_EXTENSIONS = ["docx", "pdf", "txt"];

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function acceptAttribute(limits: UploadLimits | null): string {
  return (limits?.extensions ?? DEFAULT_EXTENSIONS).map((ext) => `.${ext}`).join(",");
}

/** Why a file can't be uploaded, or `null` when it looks fine. */
export function validateFile(
  file: { name: string; size: number },
  limits: UploadLimits | null,
): string | null {
  const extensions = limits?.extensions ?? DEFAULT_EXTENSIONS;
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!extensions.includes(ext)) {
    return `Unsupported type. Upload ${extensions.map((e) => e.toUpperCase()).join(", ")} files.`;
  }
  if (file.size === 0) return "The file is empty.";
  if (limits && file.size > limits.max_bytes) {
    return `Too large (${formatBytes(file.size)}). The limit is ${formatBytes(limits.max_bytes)}.`;
  }
  return null;
}

export const DOC_STATUS: Record<DocumentStatus, { label: string; tone: string }> = {
  queued: { label: "Queued", tone: "bg-muted-foreground/60" },
  processing: { label: "Processing", tone: "bg-amber-500" },
  ready: { label: "Ready", tone: "bg-success" },
  failed: { label: "Failed", tone: "bg-destructive" },
};

export const SOURCE_STATUS: Record<SourceStatus, string> = {
  pending: "Waiting",
  syncing: "Syncing",
  ready: "Ready",
  partial: "Partly indexed",
  failed: "Failed",
};

export const STAGE_LABEL: Record<string, string> = {
  validate: "Starting",
  extract: "Reading file",
  dedupe: "Checking duplicates",
  chunk: "Splitting text",
  embed: "Creating embeddings",
  persist: "Saving",
  crawl: "Crawling",
};

/** True while the API is still working on this document (drives polling). */
export function isBusy(document: Pick<KnowledgeDocument, "status">): boolean {
  return document.status === "queued" || document.status === "processing";
}

export function documentProgress(document: KnowledgeDocument): string | null {
  if (!isBusy(document) || !document.job) return null;
  const stage = document.job.stage ? (STAGE_LABEL[document.job.stage] ?? document.job.stage) : null;
  const retry =
    document.job.attempt > 1
      ? ` · attempt ${document.job.attempt} of ${document.job.max_attempts}`
      : "";
  return `${stage ?? "Waiting for a worker"}${retry}`;
}

// ---------------------------------------------------------------------------- websites

const patterns = z
  .string()
  .transform((value) =>
    value
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
  )
  .pipe(
    z
      .array(z.string().regex(/^\/[^\s]*$/, "Patterns start with / and have no spaces."))
      .max(20, "Use at most 20 patterns."),
  );

export function websiteSchema(limits: UploadLimits | null) {
  const maxPages = limits?.max_pages_per_crawl ?? 200;
  return z.object({
    url: z
      .string()
      .trim()
      .min(1, "Enter the address of the site.")
      .refine((value) => /^https?:\/\/\S+$/i.test(value) && URL.canParse(value), {
        message: "Enter a full address starting with https:// (or http://).",
      }),
    max_pages: z
      .number({ error: "Enter a whole number." })
      .int("Enter a whole number.")
      .min(1, "Crawl at least 1 page.")
      .max(maxPages, `At most ${maxPages} pages.`),
    max_depth: z
      .number({ error: "Enter a whole number." })
      .int("Enter a whole number.")
      .min(0, "Use 0 or more.")
      .max(5, "At most 5 levels deep."),
    include: patterns,
    exclude: patterns,
    authorized: z.literal(true, { error: "Confirm you are allowed to index this site." }),
  });
}
