"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert } from "@acs/ui/components/alert";
import { Button } from "@acs/ui/components/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@acs/ui/components/tabs";

import { SelectField } from "@/components/form/fields";
import { BotIcon, FileTextIcon, GlobeIcon, SearchIcon } from "@/components/kit/icons";
import { EmptyState, ErrorState, ListSkeleton, PageHeader } from "@/components/kit/states";
import { useToast } from "@/components/kit/toast";
import { api } from "@/lib/api";
import { describeApiError } from "@/lib/api/messages";
import type { Org } from "@/lib/api/types";
import { can } from "@/lib/orgs";
import { useAsyncData } from "@/lib/use-async-data";

import { DocumentsPanel } from "./documents-panel";
import { RetrievalTester } from "./retrieval-tester";
import { WebsitesPanel } from "./websites-panel";

/** Knowledge for one chatbot at a time: files, websites and a retrieval tester. */
export function KnowledgeScreen({ org }: { org: Org }) {
  const base = `/orgs/${encodeURIComponent(org.id)}`;
  const canWrite = can(org, "knowledge:write") && org.status === "active";
  const canTest = can(org, "chatbot:test");
  const [selected, setSelected] = useState("");

  const bots = useAsyncData(() => api.listChatbots(org.id), [org.id]);
  const list = bots.data?.data ?? [];
  const chatbotId = selected || list[0]?.id || "";

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Knowledge"
        description="The documents and web pages each chatbot answers from."
      />

      {bots.error ? (
        <ErrorState title="Couldn't load chatbots" message={bots.error} onRetry={bots.reload} />
      ) : !bots.data ? (
        <ListSkeleton rows={2} label="Loading chatbots…" />
      ) : list.length === 0 ? (
        <EmptyState
          icon={<BotIcon />}
          title="Create a chatbot first"
          description="Knowledge belongs to a chatbot. Create one, then add the content it should answer from."
          action={
            can(org, "chatbot:write") ? (
              <Button asChild>
                <Link href={`${base}/chatbots/new`}>Create chatbot</Link>
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="max-w-sm">
            <SelectField
              label="Chatbot"
              value={chatbotId}
              onChange={(event) => setSelected(event.target.value)}
            >
              {list.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </SelectField>
          </div>
          {/* Keyed by chatbot so one chatbot's documents can never linger while another loads. */}
          <KnowledgeWorkspace
            key={chatbotId}
            orgId={org.id}
            chatbotId={chatbotId}
            canWrite={canWrite}
            canTest={canTest}
          />
        </>
      )}
    </div>
  );
}

function KnowledgeWorkspace({
  orgId,
  chatbotId,
  canWrite,
  canTest,
}: {
  orgId: string;
  chatbotId: string;
  canWrite: boolean;
  canTest: boolean;
}) {
  const toast = useToast();
  const limits = useAsyncData(() => api.knowledgeLimits(orgId, chatbotId), [orgId, chatbotId]);
  const documents = useAsyncData(() => api.listDocuments(orgId, chatbotId), [orgId, chatbotId]);
  const stale = documents.data?.data.filter((d) => d.needs_reindex).length ?? 0;
  const [reindexing, setReindexing] = useState(false);

  async function reindex() {
    setReindexing(true);
    try {
      const result = await api.reindex(orgId, chatbotId);
      toast.success(
        "Reindexing started",
        `${result.queued} document${result.queued === 1 ? "" : "s"} queued.`,
      );
      documents.reload();
    } catch (failure) {
      toast.error("Couldn't start reindexing", describeApiError(failure));
    } finally {
      setReindexing(false);
    }
  }

  const known = limits.data ?? null;
  return (
    <div className="grid gap-6">
      {stale > 0 && (
        <Alert>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              {stale} document{stale === 1 ? " was" : "s were"} indexed with an older embedding
              model and {stale === 1 ? "isn't" : "aren't"} searchable until reindexed.
            </span>
            {canWrite && (
              <Button
                size="sm"
                variant="outline"
                disabled={reindexing}
                onClick={() => void reindex()}
              >
                {reindexing ? "Starting…" : "Reindex now"}
              </Button>
            )}
          </div>
        </Alert>
      )}

      <Tabs defaultValue="files">
        <TabsList aria-label="Knowledge sections">
          <TabsTrigger value="files">
            <FileTextIcon />
            Documents
          </TabsTrigger>
          <TabsTrigger value="websites">
            <GlobeIcon />
            Websites
          </TabsTrigger>
          {canTest && (
            <TabsTrigger value="search">
              <SearchIcon />
              Test retrieval
            </TabsTrigger>
          )}
        </TabsList>
        <TabsContent value="files">
          <DocumentsPanel
            orgId={orgId}
            chatbotId={chatbotId}
            canWrite={canWrite}
            limits={known}
            onChanged={documents.reload}
          />
        </TabsContent>
        <TabsContent value="websites">
          <WebsitesPanel
            orgId={orgId}
            chatbotId={chatbotId}
            canWrite={canWrite}
            limits={known}
            onChanged={documents.reload}
          />
        </TabsContent>
        {canTest && (
          <TabsContent value="search">
            <RetrievalTester orgId={orgId} chatbotId={chatbotId} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
