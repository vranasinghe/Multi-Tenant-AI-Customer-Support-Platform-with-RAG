import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import type { KnowledgeDocument, UploadLimits } from "@/lib/api/types";

import {
  acceptAttribute,
  documentProgress,
  formatBytes,
  isBusy,
  validateFile,
  websiteSchema,
} from "./knowledge";

const LIMITS: UploadLimits = {
  max_bytes: 1024 * 1024,
  extensions: ["docx", "pdf", "txt"],
  max_documents: 500,
  max_pages_per_crawl: 100,
};

const doc = (overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument => ({
  id: "d1",
  source_id: "s1",
  title: "a.txt",
  uri: "a.txt",
  mime_type: "text/plain",
  size_bytes: 10,
  status: "ready",
  error_code: null,
  error_message: null,
  page_count: null,
  chunk_count: 1,
  token_count: 3,
  version: 1,
  embedding_model: "hash-v1",
  needs_reindex: false,
  job: null,
  created_at: "2026-11-22T00:00:00Z",
  updated_at: "2026-11-22T00:00:00Z",
  ...overrides,
});

describe("validateFile", () => {
  it("accepts supported types within the size limit", () => {
    expect(validateFile({ name: "Policy.PDF", size: 100 }, LIMITS)).toBeNull();
    expect(validateFile({ name: "a.docx", size: 100 }, LIMITS)).toBeNull();
  });

  it("rejects unsupported extensions, empty and oversized files", () => {
    expect(validateFile({ name: "virus.exe", size: 100 }, LIMITS)).toMatch(/Unsupported type/);
    expect(validateFile({ name: "noextension", size: 100 }, LIMITS)).toMatch(/Unsupported type/);
    expect(validateFile({ name: "a.txt", size: 0 }, LIMITS)).toBe("The file is empty.");
    expect(validateFile({ name: "a.txt", size: 2 * 1024 * 1024 }, LIMITS)).toMatch(/Too large/);
  });

  it("falls back to default extensions before limits load", () => {
    expect(validateFile({ name: "a.txt", size: 5 }, null)).toBeNull();
    expect(acceptAttribute(null)).toBe(".docx,.pdf,.txt");
  });
});

describe("formatting and status helpers", () => {
  it("formats sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("knows which documents are still being worked on", () => {
    expect(isBusy(doc({ status: "queued" }))).toBe(true);
    expect(isBusy(doc({ status: "processing" }))).toBe(true);
    expect(isBusy(doc({ status: "ready" }))).toBe(false);
    expect(isBusy(doc({ status: "failed" }))).toBe(false);
  });

  it("describes progress including retries", () => {
    const job = {
      id: "j",
      kind: "process_document" as const,
      status: "processing" as const,
      stage: "embed",
      attempt: 2,
      max_attempts: 4,
      error_code: null,
      stats: {},
      queued_at: "",
      finished_at: null,
    };
    expect(documentProgress(doc({ status: "processing", job }))).toBe(
      "Creating embeddings · attempt 2 of 4",
    );
    expect(documentProgress(doc({ status: "queued", job: null }))).toBeNull();
    expect(documentProgress(doc({ status: "ready", job }))).toBeNull();
  });
});

describe("websiteSchema", () => {
  const valid = {
    url: "https://help.example.com/",
    max_pages: 50,
    max_depth: 2,
    include: "/docs/*\n\n/help/*",
    exclude: "",
    authorized: true,
  };

  it("parses patterns one per line and requires authorization", () => {
    const parsed = websiteSchema(LIMITS).safeParse(valid);
    expect(parsed.success && parsed.data.include).toEqual(["/docs/*", "/help/*"]);
    const refused = websiteSchema(LIMITS).safeParse({ ...valid, authorized: false });
    expect(refused.success).toBe(false);
  });

  it.each([
    [{ url: "" }, "url"],
    [{ url: "help.example.com" }, "url"],
    [{ url: "ftp://example.com" }, "url"],
    [{ max_pages: 0 }, "max_pages"],
    [{ max_pages: 101 }, "max_pages"],
    [{ max_depth: 9 }, "max_depth"],
    [{ include: "no-slash" }, "include"],
    [{ exclude: "/ has space" }, "exclude"],
  ])("rejects %o", (override, field) => {
    const parsed = websiteSchema(LIMITS).safeParse({ ...valid, ...override });
    expect(parsed.success).toBe(false);
    expect(!parsed.success && parsed.error.issues.map((i) => i.path[0])).toContain(field);
  });
});

describe("api client upload", () => {
  it("sends the raw bytes with the file type, CSRF header and credentials", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "d1" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = createApiClient({ baseUrl: "http://api.test/", fetchImpl });
    const file = new Blob(["hello"], { type: "text/plain" });

    await client.upload("/orgs/o/documents", file, "text/plain");

    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe("http://api.test/api/v1/orgs/o/documents");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(file);
    expect(init.credentials).toBe("include");
    expect(init.headers["Content-Type"]).toBe("text/plain");
    expect(init.headers["X-Requested-With"]).toBe("platform");
  });
});
