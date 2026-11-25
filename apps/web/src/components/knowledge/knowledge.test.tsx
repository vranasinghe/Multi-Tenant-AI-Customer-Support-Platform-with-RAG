// @vitest-environment jsdom
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import type * as ApiClientModule from "@/lib/api/client";
import type {
  IngestionJob,
  KnowledgeDocument,
  KnowledgeSource,
  UploadLimits,
} from "@/lib/api/types";

const mocks = vi.hoisted(() => ({
  listDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  reprocessDocument: vi.fn(),
  listChunks: vi.fn(),
  listSources: vi.fn(),
  createWebsite: vi.fn(),
  syncSource: vi.fn(),
  deleteSource: vi.fn(),
  searchKnowledge: vi.fn(),
}));
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/lib/api/client");
  return { ApiError: actual.ApiError, api: mocks };
});

import { ToastProvider } from "../kit/toast";
import { DocumentsPanel } from "./documents-panel";
import { RetrievalTester } from "./retrieval-tester";
import { WebsitesPanel } from "./websites-panel";

const LIMITS: UploadLimits = {
  max_bytes: 1024,
  extensions: ["docx", "pdf", "txt"],
  max_documents: 500,
  max_pages_per_crawl: 100,
};

const job = (overrides: Partial<IngestionJob> = {}): IngestionJob => ({
  id: "j1",
  kind: "process_document",
  status: "succeeded",
  stage: "done",
  attempt: 1,
  max_attempts: 4,
  error_code: null,
  stats: {},
  queued_at: "2026-11-22T00:00:00Z",
  finished_at: null,
  ...overrides,
});

const document = (overrides: Partial<KnowledgeDocument> = {}): KnowledgeDocument => ({
  id: "d1",
  source_id: "s1",
  title: "Shipping.pdf",
  uri: "Shipping.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  status: "ready",
  error_code: null,
  error_message: null,
  page_count: 3,
  chunk_count: 4,
  token_count: 400,
  version: 1,
  embedding_model: "hash-v1",
  needs_reindex: false,
  job: job(),
  created_at: "2026-11-22T00:00:00Z",
  updated_at: "2026-11-22T00:00:00Z",
  ...overrides,
});

const listing = (...docs: KnowledgeDocument[]) => ({ data: docs, embedding_model: "hash-v1" });

function renderDocs(canWrite = true) {
  // Drag-and-drop bypasses the picker's accept filter, so the panel must validate on its own.
  const user = userEvent.setup({ applyAccept: false });
  const onChanged = vi.fn();
  render(
    <ToastProvider>
      <DocumentsPanel
        orgId="o1"
        chatbotId="b1"
        canWrite={canWrite}
        limits={LIMITS}
        onChanged={onChanged}
      />
    </ToastProvider>,
  );
  return { user, onChanged };
}

const file = (name: string, size = 10, type = "text/plain") =>
  new File([new Uint8Array(size)], name, { type });

describe("DocumentsPanel", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.listDocuments.mockResolvedValue(listing(document()));
  });

  it("shows a skeleton, then documents with status and details", async () => {
    renderDocs();

    expect(screen.getByRole("status")).toHaveTextContent("Loading documents…");
    const table = await screen.findByRole("table", { name: "Documents" });
    const row = within(table).getByRole("row", { name: /Shipping\.pdf/ });
    expect(within(row).getByText("Ready")).toBeInTheDocument();
    expect(within(row).getByText("4 passages")).toBeInTheDocument();
  });

  it("shows an empty state with guidance", async () => {
    mocks.listDocuments.mockResolvedValueOnce(listing());
    renderDocs();

    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeInTheDocument();
    expect(screen.getByText(/processed in the background/)).toBeInTheDocument();
  });

  it("recovers from a load error", async () => {
    mocks.listDocuments
      .mockRejectedValueOnce(new ApiError({ status: 500, code: "internal_error", message: "x" }))
      .mockResolvedValue(listing(document()));
    const { user } = renderDocs();

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load documents");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("explains why a failed document failed and offers a retry", async () => {
    mocks.listDocuments.mockResolvedValue(
      listing(
        document({
          status: "failed",
          error_code: "encrypted",
          error_message: "The file is password-protected. Remove the password and upload it again.",
          job: job({ status: "failed", error_code: "encrypted" }),
        }),
      ),
    );
    mocks.reprocessDocument.mockResolvedValue(document({ status: "queued" }));
    const { user } = renderDocs();

    expect(await screen.findByText(/password-protected/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Retry/ }));

    expect(mocks.reprocessDocument).toHaveBeenCalledWith("o1", "b1", "d1");
    expect(await screen.findByText("Reprocessing started")).toBeInTheDocument();
  });

  it("polls while something is processing and stops when it is ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mocks.listDocuments
        .mockResolvedValueOnce(
          listing(
            document({
              status: "processing",
              job: job({ status: "processing", stage: "embed", attempt: 2 }),
            }),
          ),
        )
        .mockResolvedValue(listing(document()));
      renderDocs();

      expect(await screen.findByText("Processing")).toBeInTheDocument();
      expect(screen.getByText("Creating embeddings · attempt 2 of 4")).toBeInTheDocument();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });
      expect(await screen.findByText("Ready")).toBeInTheDocument();
      const calls = mocks.listDocuments.mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(6000);
      });
      expect(mocks.listDocuments.mock.calls.length).toBe(calls); // polling stopped
    } finally {
      vi.useRealTimers();
    }
  });

  it("validates files before uploading and reports each result", async () => {
    mocks.uploadDocument.mockResolvedValue(document());
    const { user, onChanged } = renderDocs();
    await screen.findByRole("table");

    await user.upload(screen.getByLabelText("Choose files to upload"), [
      file("notes.txt"),
      new File(["x"], "run.exe", { type: "application/octet-stream" }),
      file("big.txt", 4096),
      file("empty.txt", 0),
    ]);

    const uploads = screen.getByRole("list", { name: "Uploads" });
    expect(await within(uploads).findByText(/Uploaded\. Processing continues/)).toBeInTheDocument();
    expect(within(uploads).getByText(/Unsupported type/)).toBeInTheDocument();
    expect(within(uploads).getByText(/Too large/)).toBeInTheDocument();
    expect(within(uploads).getByText("The file is empty.")).toBeInTheDocument();
    expect(mocks.uploadDocument).toHaveBeenCalledTimes(1);
    expect(mocks.uploadDocument.mock.calls[0]![2].name).toBe("notes.txt");
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows server-side upload errors in plain language", async () => {
    mocks.uploadDocument.mockRejectedValue(
      new ApiError({ status: 409, code: "duplicate_document", message: "dup" }),
    );
    const { user } = renderDocs();
    await screen.findByRole("table");

    await user.upload(screen.getByLabelText("Choose files to upload"), file("again.txt"));

    expect(
      await screen.findByText("This exact file was already uploaded to this chatbot."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dismiss again.txt" }));
    expect(screen.queryByText("again.txt")).not.toBeInTheDocument();
  });

  it("deletes only after confirmation", async () => {
    mocks.deleteDocument.mockResolvedValue(undefined);
    const { user } = renderDocs();
    await screen.findByRole("table");

    await user.click(screen.getByRole("button", { name: "Delete Shipping.pdf" }));
    const dialog = screen.getByRole("alertdialog", { name: "Delete Shipping.pdf?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mocks.deleteDocument).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete Shipping.pdf" }));
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Delete document" }),
    );

    await waitFor(() => expect(mocks.deleteDocument).toHaveBeenCalledWith("o1", "b1", "d1"));
    expect(await screen.findByText("Document deleted")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("previews passages as plain text and pages through them", async () => {
    mocks.listChunks.mockImplementation(async (_o, _b, _d, offset: number) => ({
      total: 7,
      data: [
        {
          id: `c${offset}`,
          ordinal: offset,
          content:
            offset === 0 ? "<img src=x onerror=alert(1)> Standard shipping" : "Second page text",
          heading_path: ["Shipping", "Domestic"],
          page_start: 2,
          page_end: 3,
          token_count: 12,
        },
      ],
    }));
    const { user } = renderDocs();
    await screen.findByRole("table");

    await user.click(screen.getByRole("button", { name: /Passages/ }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(/Standard shipping/)).toHaveTextContent(
      "<img src=x onerror=alert(1)>",
    );
    expect(dialog.querySelector("img")).toBeNull();
    expect(within(dialog).getByText(/Shipping › Domestic · page 2–3/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Next" }));
    expect(await within(dialog).findByText("Second page text")).toBeInTheDocument();
    expect(mocks.listChunks).toHaveBeenLastCalledWith("o1", "b1", "d1", 5, 5);
  });

  it("is read-only for viewers", async () => {
    renderDocs(false);

    await screen.findByRole("table");
    expect(screen.queryByLabelText("Choose files to upload")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reprocess/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Passages/ })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------------------ websites

const source = (overrides: Partial<KnowledgeSource> = {}): KnowledgeSource => ({
  id: "s1",
  kind: "website",
  name: "help.example.com",
  status: "ready",
  config: { start_url: "https://help.example.com/", max_pages: 50 },
  stats: { documents: 12, failed: 1 },
  last_synced_at: "2026-11-22T00:00:00Z",
  created_at: "2026-11-22T00:00:00Z",
  job: null,
  ...overrides,
});

describe("WebsitesPanel", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.listSources.mockResolvedValue({ data: [source()] });
  });

  function renderSites(canWrite = true) {
    const user = userEvent.setup();
    render(
      <ToastProvider>
        <WebsitesPanel orgId="o1" chatbotId="b1" canWrite={canWrite} limits={LIMITS} />
      </ToastProvider>,
    );
    return user;
  }

  it("lists websites with their state and summary", async () => {
    renderSites();

    const list = await screen.findByRole("list", { name: "Websites" });
    expect(within(list).getAllByText("help.example.com").length).toBeGreaterThan(0);
    expect(within(list).getByText(/12 pages · 1 failed/)).toBeInTheDocument();
  });

  it("requires a valid address and the authorization checkbox", async () => {
    const user = renderSites();
    await screen.findByRole("list", { name: "Websites" });

    await user.click(screen.getByRole("button", { name: "Add website" }));
    expect(screen.getByText("Enter the address of the site.")).toBeInTheDocument();
    expect(screen.getByLabelText("Starting address")).toHaveFocus();

    await user.type(screen.getByLabelText("Starting address"), "https://help.example.com/");
    await user.click(screen.getByRole("button", { name: "Add website" }));
    expect(screen.getByText("Confirm you are allowed to index this site.")).toBeInTheDocument();
    expect(mocks.createWebsite).not.toHaveBeenCalled();
  });

  it("submits the crawl settings and parsed path patterns", async () => {
    mocks.createWebsite.mockResolvedValue(source({ status: "syncing" }));
    const user = renderSites();
    await screen.findByRole("list", { name: "Websites" });

    await user.type(screen.getByLabelText("Starting address"), "https://help.example.com/");
    await user.type(screen.getByLabelText(/Only these paths/), "/docs/*{Enter}/help/*");
    await user.click(screen.getByLabelText(/I own this website/));
    await user.click(screen.getByRole("button", { name: "Add website" }));

    await waitFor(() => expect(mocks.createWebsite).toHaveBeenCalledTimes(1));
    expect(mocks.createWebsite).toHaveBeenCalledWith("o1", "b1", {
      url: "https://help.example.com/",
      max_pages: 50,
      max_depth: 2,
      include: ["/docs/*", "/help/*"],
      exclude: [],
      confirm_authorized: true,
    });
    expect(await screen.findByText("Website added")).toBeInTheDocument();
  });

  it("shows when the server refuses a private address", async () => {
    mocks.createWebsite.mockRejectedValue(
      new ApiError({
        status: 422,
        code: "blocked_destination",
        message: "This address isn't allowed.",
        fieldErrors: { url: "This address isn't allowed. Only public websites can be crawled." },
      }),
    );
    const user = renderSites();
    await screen.findByRole("list", { name: "Websites" });

    await user.type(screen.getByLabelText("Starting address"), "http://169.254.169.254/");
    await user.click(screen.getByLabelText(/I own this website/));
    await user.click(screen.getByRole("button", { name: "Add website" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only public websites can be crawled",
    );
    expect(screen.getByLabelText("Starting address")).toHaveAttribute("aria-invalid", "true");
  });

  it("syncs and removes websites (removal needs confirmation)", async () => {
    mocks.syncSource.mockResolvedValue(source({ status: "syncing" }));
    mocks.deleteSource.mockResolvedValue(undefined);
    const user = renderSites();
    await screen.findByRole("list", { name: "Websites" });

    await user.click(screen.getByRole("button", { name: /Sync now/ }));
    expect(mocks.syncSource).toHaveBeenCalledWith("o1", "b1", "s1");
    expect(await screen.findByRole("button", { name: /Syncing/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Remove help.example.com" }));
    expect(mocks.deleteSource).not.toHaveBeenCalled();
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Remove website" }),
    );
    await waitFor(() => expect(mocks.deleteSource).toHaveBeenCalledWith("o1", "b1", "s1"));
  });

  it("hides the form and actions from read-only roles", async () => {
    renderSites(false);

    await screen.findByRole("list", { name: "Websites" });
    expect(screen.queryByRole("form", { name: "Add a website" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sync now/ })).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------------------------ retrieval

describe("RetrievalTester", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it("searches with the chosen method and shows scored passages as text", async () => {
    mocks.searchKnowledge.mockResolvedValue({
      mode: "vector",
      embedding_model: "hash-v1",
      took_ms: 12,
      results: [
        {
          chunk_id: "c1",
          document_id: "d1",
          source_id: "s1",
          document_title: "Returns.txt",
          uri: "Returns.txt",
          ordinal: 0,
          content: "<script>alert(1)</script> Returns within thirty days.",
          heading_path: ["Returns"],
          page_start: null,
          page_end: null,
          score: 0.03,
          vector_score: 0.4567,
          vector_rank: 1,
          keyword_rank: null,
        },
      ],
    });
    const user = userEvent.setup();
    render(<RetrievalTester orgId="o1" chatbotId="b1" />);

    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
    await user.type(screen.getByLabelText("Question"), "refund window");
    await user.selectOptions(screen.getByLabelText("Method"), "vector");
    await user.click(screen.getByRole("button", { name: "Search" }));

    const results = await screen.findByRole("region", { name: "Search results" });
    expect(mocks.searchKnowledge).toHaveBeenCalledWith("o1", "b1", {
      query: "refund window",
      mode: "vector",
    });
    expect(within(results).getByText(/Returns within thirty days/)).toHaveTextContent(
      "<script>alert(1)</script>",
    );
    expect(results.querySelector("script")).toBeNull();
    expect(within(results).getByText(/similarity 0\.457 · vector #1/)).toBeInTheDocument();
  });

  it("explains an empty result and surfaces errors", async () => {
    mocks.searchKnowledge
      .mockResolvedValueOnce({
        results: [],
        mode: "hybrid",
        embedding_model: "hash-v1",
        took_ms: 3,
      })
      .mockRejectedValueOnce(new ApiError({ status: 429, code: "rate_limited", message: "x" }));
    const user = userEvent.setup();
    render(<RetrievalTester orgId="o1" chatbotId="b1" />);

    await user.type(screen.getByLabelText("Question"), "nothing");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(
      await screen.findByRole("heading", { name: "No relevant passages" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many attempts/);
  });
});
