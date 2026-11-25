"use client";

import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

import { Button } from "@acs/ui/components/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@acs/ui/components/dialog";
import { cn } from "@acs/ui/lib/utils";

import { ConfirmDialog } from "@/components/kit/confirm-dialog";
import { FileTextIcon, GlobeIcon, TrashIcon, UploadIcon, XIcon } from "@/components/kit/icons";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/kit/states";
import { useToast } from "@/components/kit/toast";
import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { KnowledgeDocument, UploadLimits } from "@/lib/api/types";
import {
  DOC_STATUS,
  acceptAttribute,
  documentProgress,
  formatBytes,
  isBusy,
  validateFile,
} from "@/lib/knowledge";
import { useAsyncData } from "@/lib/use-async-data";
import { usePolling } from "@/lib/use-polling";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

interface UploadItem {
  key: number;
  name: string;
  state: "uploading" | "done" | "error";
  message?: string;
}

export function DocumentStatusBadge({ document }: { document: KnowledgeDocument }) {
  const meta = DOC_STATUS[document.status];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium">
      <span aria-hidden="true" className={cn("size-1.5 rounded-full", meta.tone)} />
      {meta.label}
    </span>
  );
}

/**
 * Files for one chatbot: upload, live processing status, errors with a way out, chunk preview,
 * reprocess and delete. Statuses refresh by polling while anything is queued or processing.
 */
export function DocumentsPanel({
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
  const inputRef = useRef<HTMLInputElement>(null);
  const nextKey = useRef(1);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const [deleting, setDeleting] = useState<KnowledgeDocument | null>(null);
  const [viewing, setViewing] = useState<KnowledgeDocument | null>(null);

  const { data, error, reload, update } = useAsyncData(
    () => api.listDocuments(orgId, chatbotId),
    [orgId, chatbotId],
  );
  const documents = data?.data ?? null;
  usePolling(Boolean(documents?.some(isBusy)), reload);

  async function uploadFiles(files: File[]) {
    for (const file of files) {
      const key = nextKey.current++;
      const problem = validateFile(file, limits);
      if (problem) {
        setUploads((current) => [
          ...current,
          { key, name: file.name, state: "error", message: problem },
        ]);
        continue;
      }
      setUploads((current) => [...current, { key, name: file.name, state: "uploading" }]);
      try {
        await api.uploadDocument(orgId, chatbotId, file);
        setUploads((current) =>
          current.map((u) => (u.key === key ? { ...u, state: "done" as const } : u)),
        );
        reload();
        onChanged?.();
      } catch (failure) {
        setUploads((current) =>
          current.map((u) =>
            u.key === key
              ? { ...u, state: "error" as const, message: describeApiError(failure) }
              : u,
          ),
        );
      }
    }
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = ""; // allow picking the same file again after a fix
    if (files.length > 0) void uploadFiles(files);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (!canWrite) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) void uploadFiles(files);
  }

  async function reprocess(document: KnowledgeDocument) {
    try {
      const updated = await api.reprocessDocument(orgId, chatbotId, document.id);
      update(
        (current) =>
          current && {
            ...current,
            data: current.data.map((d) => (d.id === document.id ? updated : d)),
          },
      );
      toast.success("Reprocessing started", document.title);
    } catch (failure) {
      toast.error("Couldn't reprocess", describeApiError(failure));
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    const target = deleting;
    try {
      await api.deleteDocument(orgId, chatbotId, target.id);
      update(
        (current) =>
          current && { ...current, data: current.data.filter((d) => d.id !== target.id) },
      );
      setDeleting(null);
      toast.success("Document deleted", "Its text and vectors were removed.");
      onChanged?.();
    } catch (failure) {
      setDeleting(null);
      toast.error("Couldn't delete", describeApiError(failure));
    }
  }

  return (
    <div className="grid gap-6">
      {canWrite && (
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "grid justify-items-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragging && "border-foreground bg-accent/40",
          )}
        >
          <span className="text-muted-foreground">
            <UploadIcon width={24} height={24} />
          </span>
          <p className="text-sm font-medium">Drag files here, or choose them</p>
          <p className="text-sm text-muted-foreground">
            {(limits?.extensions ?? ["pdf", "docx", "txt"]).map((e) => e.toUpperCase()).join(", ")}
            {limits ? ` · up to ${formatBytes(limits.max_bytes)} each` : ""}
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={acceptAttribute(limits)}
            onChange={onPick}
            className="sr-only"
            aria-label="Choose files to upload"
          />
          <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>
            Choose files
          </Button>
        </div>
      )}

      {uploads.length > 0 && (
        <ul aria-label="Uploads" aria-live="polite" className="grid gap-2">
          {uploads.map((item) => (
            <li
              key={item.key}
              className={cn(
                "flex items-start justify-between gap-3 rounded-lg border px-3 py-2 text-sm",
                item.state === "error" && "border-destructive/40",
              )}
            >
              <span className="grid min-w-0 gap-0.5">
                <span className="truncate font-medium">{item.name}</span>
                <span
                  className={cn(
                    "text-muted-foreground",
                    item.state === "error" && "text-destructive",
                  )}
                >
                  {item.state === "uploading" && "Uploading…"}
                  {item.state === "done" && "Uploaded. Processing continues in the background."}
                  {item.state === "error" && item.message}
                </span>
              </span>
              {item.state !== "uploading" && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Dismiss ${item.name}`}
                  onClick={() => setUploads((current) => current.filter((u) => u.key !== item.key))}
                >
                  <XIcon />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {error ? (
        <ErrorState title="Couldn't load documents" message={error} onRetry={reload} />
      ) : documents === null ? (
        <ListSkeleton rows={3} label="Loading documents…" />
      ) : documents.length === 0 ? (
        <EmptyState
          icon={<FileTextIcon />}
          title="No documents yet"
          description={
            canWrite
              ? "Upload PDF, Word or text files. They are processed in the background and become searchable when ready."
              : "Nothing has been added to this chatbot yet."
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Documents</caption>
            <thead className="border-b bg-muted/40 text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">
                  Name
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Status
                </th>
                <th scope="col" className="hidden px-4 py-2 font-medium md:table-cell">
                  Details
                </th>
                <th scope="col" className="px-4 py-2 text-right font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {documents.map((document) => {
                const progress = documentProgress(document);
                return (
                  <tr key={document.id}>
                    <td className="max-w-64 px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="shrink-0 text-muted-foreground">
                          {document.mime_type === "text/html" ? <GlobeIcon /> : <FileTextIcon />}
                        </span>
                        <span className="grid min-w-0">
                          <span className="truncate font-medium">{document.title}</span>
                          {document.mime_type === "text/html" && (
                            <span className="truncate text-xs text-muted-foreground">
                              {document.uri}
                            </span>
                          )}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="grid gap-1">
                        <DocumentStatusBadge document={document} />
                        {progress && (
                          <span className="text-xs text-muted-foreground">{progress}</span>
                        )}
                        {document.status === "failed" && document.error_message && (
                          <span className="max-w-60 text-xs text-destructive">
                            {document.error_message}
                          </span>
                        )}
                        {document.needs_reindex && (
                          <span className="text-xs text-muted-foreground">Needs reindexing</span>
                        )}
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      <div className="grid text-xs">
                        <span>
                          {formatBytes(document.size_bytes)}
                          {document.page_count ? ` · ${document.page_count} pages` : ""}
                        </span>
                        <span>{document.chunk_count} passages</span>
                        <span>
                          <time dateTime={document.updated_at}>
                            {dateFormat.format(new Date(document.updated_at))}
                          </time>
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap justify-end gap-1">
                        {document.chunk_count > 0 && (
                          <Button size="sm" variant="ghost" onClick={() => setViewing(document)}>
                            Passages<span className="sr-only"> of {document.title}</span>
                          </Button>
                        )}
                        {canWrite && !isBusy(document) && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void reprocess(document)}
                          >
                            {document.status === "failed" ? "Retry" : "Reprocess"}
                            <span className="sr-only"> {document.title}</span>
                          </Button>
                        )}
                        {canWrite && (
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            aria-label={`Delete ${document.title}`}
                            onClick={() => setDeleting(document)}
                          >
                            <TrashIcon />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => !open && setDeleting(null)}
        title={`Delete ${deleting?.title ?? "document"}?`}
        description="Its text and search vectors are removed immediately and the original file is deleted from storage. This can't be undone."
        confirmLabel="Delete document"
        destructive
        onConfirm={confirmDelete}
      />
      <ChunkPreviewDialog
        orgId={orgId}
        chatbotId={chatbotId}
        document={viewing}
        onClose={() => setViewing(null)}
      />
    </div>
  );
}

const PAGE = 5;

function ChunkPreviewDialog({
  orgId,
  chatbotId,
  document,
  onClose,
}: {
  orgId: string;
  chatbotId: string;
  document: KnowledgeDocument | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={document !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85dvh] max-w-2xl overflow-y-auto">
        {document && <ChunkList orgId={orgId} chatbotId={chatbotId} document={document} />}
        <DialogClose asChild>
          <Button variant="outline" className="justify-self-end">
            Close
          </Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}

function ChunkList({
  orgId,
  chatbotId,
  document,
}: {
  orgId: string;
  chatbotId: string;
  document: KnowledgeDocument;
}) {
  const [offset, setOffset] = useState(0);
  const { data, error, reload } = useAsyncData(
    () => api.listChunks(orgId, chatbotId, document.id, offset, PAGE),
    [orgId, chatbotId, document.id, offset],
  );
  return (
    <div className="grid gap-4">
      <div className="grid gap-1">
        <DialogTitle>Passages</DialogTitle>
        <DialogDescription>
          How <strong className="font-medium text-foreground">{document.title}</strong> is split for
          search. {data ? `${data.total} passages.` : ""}
        </DialogDescription>
      </div>
      {error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data ? (
        <ListSkeleton rows={2} label="Loading passages…" />
      ) : (
        <ol className="grid gap-3" start={offset + 1}>
          {data.data.map((chunk) => (
            <li key={chunk.id} className="grid gap-1 rounded-lg border p-3 text-sm">
              <p className="text-xs text-muted-foreground">
                #{chunk.ordinal + 1}
                {chunk.heading_path.length > 0 && ` · ${chunk.heading_path.join(" › ")}`}
                {chunk.page_start != null &&
                  ` · page ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""}`}
                {` · ~${chunk.token_count} tokens`}
              </p>
              {/* Rendered as text: document content is untrusted and never interpreted as HTML. */}
              <p className="break-words whitespace-pre-wrap">{chunk.content}</p>
            </li>
          ))}
        </ol>
      )}
      {data && data.total > PAGE && (
        <div className="flex items-center justify-between">
          <Button
            variant="outline"
            size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={offset + PAGE >= data.total}
            onClick={() => setOffset(offset + PAGE)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
