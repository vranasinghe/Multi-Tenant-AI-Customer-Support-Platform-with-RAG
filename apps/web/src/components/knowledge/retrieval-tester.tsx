"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Input } from "@acs/ui/components/input";
import { Label } from "@acs/ui/components/label";
import { Select } from "@acs/ui/components/select";

import { SearchIcon } from "@/components/kit/icons";
import { EmptyState } from "@/components/kit/states";
import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { SearchMode, SearchResponse } from "@/lib/api/types";

const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid (vector + keyword)" },
  { value: "vector", label: "Vector only" },
  { value: "keyword", label: "Keyword only" },
];

/**
 * Retrieval debugger: shows which passages the chatbot would be given for a question, with scores.
 * Passage text is untrusted document content, so it is only ever rendered as plain text.
 */
export function RetrievalTester({ orgId, chatbotId }: { orgId: string; chatbotId: string }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<(SearchResponse & { asked: string }) | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const asked = query.trim();
    if (!asked || pending) return;
    setPending(true);
    setError(null);
    try {
      setResponse({
        ...(await api.searchKnowledge(orgId, chatbotId, { query: asked, mode })),
        asked,
      });
    } catch (failure) {
      setError(describeApiError(failure));
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="grid gap-6">
      <form
        onSubmit={onSubmit}
        className="grid max-w-3xl gap-3 sm:grid-cols-[1fr_14rem_auto] sm:items-end"
        role="search"
        aria-label="Test retrieval"
      >
        <div className="grid gap-1.5">
          <Label htmlFor="retrieval-query">Question</Label>
          <Input
            id="retrieval-query"
            value={query}
            maxLength={1000}
            placeholder="e.g. How long do refunds take?"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="retrieval-mode">Method</Label>
          <Select
            id="retrieval-mode"
            value={mode}
            onChange={(event) => setMode(event.target.value as SearchMode)}
          >
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" disabled={pending || query.trim() === ""}>
          <SearchIcon />
          {pending ? "Searching…" : "Search"}
        </Button>
      </form>

      {error && <Alert variant="destructive">{error}</Alert>}

      {response && (
        <section aria-label="Search results" aria-live="polite" className="grid gap-3">
          <p className="text-sm text-muted-foreground">
            {response.results.length} passage{response.results.length === 1 ? "" : "s"} for “
            {response.asked}” · {response.mode} · {response.took_ms} ms · model{" "}
            {response.embedding_model}
          </p>
          {response.results.length === 0 ? (
            <EmptyState
              icon={<SearchIcon />}
              title="No relevant passages"
              description="Nothing matched. Check that documents are Ready (and reindexed if the embedding model changed)."
            />
          ) : (
            <ol className="grid gap-3">
              {response.results.map((result, index) => (
                <li key={result.chunk_id} className="grid gap-2 rounded-xl border bg-card p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="min-w-0 truncate text-sm font-medium">
                      {index + 1}. {result.document_title}
                      <span className="font-normal text-muted-foreground">
                        {result.heading_path.length > 0 && ` · ${result.heading_path.join(" › ")}`}
                        {result.page_start != null &&
                          ` · p. ${result.page_start}${result.page_end && result.page_end !== result.page_start ? `–${result.page_end}` : ""}`}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      similarity {result.vector_score.toFixed(3)}
                      {result.vector_rank != null && ` · vector #${result.vector_rank}`}
                      {result.keyword_rank != null && ` · keyword #${result.keyword_rank}`}
                    </p>
                  </div>
                  <p className="text-sm break-words whitespace-pre-wrap">{result.content}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
