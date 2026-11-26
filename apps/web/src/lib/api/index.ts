import { createApiClient, publicApiBaseUrl, type ApiClient } from "./client";
import type { ChatMessage } from "../chat";
import type {
  AssignableRole,
  AuditPage,
  Chatbot,
  ChatbotList,
  ChatbotOptions,
  ChatbotStatus,
  ChunkPreview,
  CreateChatbotBody,
  DocumentList,
  DocumentStatus,
  KnowledgeDocument,
  KnowledgeSource,
  SearchMode,
  SearchResponse,
  UploadLimits,
  WebsiteSourceBody,
  Invitation,
  InvitationPreview,
  MeResponse,
  Member,
  Org,
  OrgRole,
  Page,
  SessionInfo,
  SignupResponse,
  UpdateChatbotBody,
  User,
  AnalyticsSummary,
  ConversationDetail,
  ConversationExport,
  ConversationList,
  InboxFilters,
  KnowledgeGap,
  MessagePage,
  RetentionSettings,
  Timeseries,
  UnansweredGroup,
} from "./types";

export { ApiError } from "./client";
export type * from "./types";

/** Every endpoint the dashboard uses, as typed functions. Org ids appear only in paths. */
export function createEndpoints(client: ApiClient) {
  const org = (orgId: string) => `/orgs/${encodeURIComponent(orgId)}`;
  const bot = (orgId: string, botId: string) =>
    `${org(orgId)}/chatbots/${encodeURIComponent(botId)}`;
  return {
    createConversation: (orgId: string, botId: string) =>
      client.post<{ id: string }>(`${bot(orgId, botId)}/conversations`),
    listChatConversations: (orgId: string, botId: string) =>
      client.get<{ data: { id: string; channel: string; created_at: string }[] }>(
        `${bot(orgId, botId)}/conversations`,
      ),
    getConversation: (orgId: string, id: string) =>
      client.get<{ messages: ChatMessage[] }>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}`,
      ),
    chatFeedback: (orgId: string, conversationId: string, messageId: string, rating: number) =>
      client.put<{ status: string }>(
        `${org(orgId)}/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}/feedback`,
        { rating },
      ),
    listInbox: (orgId: string, filters: InboxFilters = {}) => {
      const query = new URLSearchParams();
      if (filters.chatbot_id) query.set("chatbot_id", filters.chatbot_id);
      if (filters.channel) query.set("channel", filters.channel);
      if (filters.status) query.set("status", filters.status);
      if (filters.from) query.set("from", filters.from);
      if (filters.to) query.set("to", filters.to);
      if (filters.feedback) query.set("feedback", filters.feedback);
      if (filters.satisfaction) query.set("satisfaction", filters.satisfaction);
      if (filters.unanswered) query.set("unanswered", "true");
      if (filters.grounded === false) query.set("grounded", "false");
      if (filters.q?.trim()) query.set("q", filters.q.trim());
      if (filters.cursor) query.set("cursor", filters.cursor);
      if (filters.limit) query.set("limit", String(filters.limit));
      const suffix = query.size ? `?${query.toString()}` : "";
      return client.get<ConversationList>(`${org(orgId)}/conversations${suffix}`);
    },
    getConversationDetail: (orgId: string, id: string) =>
      client.get<ConversationDetail>(`${org(orgId)}/conversations/${encodeURIComponent(id)}`),
    listMessages: (orgId: string, id: string, cursor: string) => {
      const query = new URLSearchParams({ limit: "50", cursor });
      return client.get<MessagePage>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}/messages?${query.toString()}`,
      );
    },
    updateConversationStatus: (
      orgId: string,
      id: string,
      status: "open" | "resolved" | "unresolved",
    ) =>
      client.patch<{ id: string; status: string }>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}`,
        { status },
      ),
    deleteConversation: (orgId: string, id: string) =>
      client.delete(`${org(orgId)}/conversations/${encodeURIComponent(id)}`),
    recordSatisfaction: (orgId: string, id: string, score: number, comment?: string) =>
      client.put<{ id: string; satisfaction_score: number }>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}/satisfaction`,
        { score, comment },
      ),
    requestHandoff: (orgId: string, id: string, reason: string, contact?: string) =>
      client.post<{ id: string; status: string; handoff_status: string }>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}/handoff`,
        { reason, contact },
      ),
    updateHandoff: (
      orgId: string,
      id: string,
      status: "acknowledged" | "completed" | "cancelled",
    ) =>
      client.patch<{ id: string; status: string; handoff_status: string }>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}/handoff`,
        { status },
      ),
    markUnanswered: (orgId: string, id: string, reason = "marked_unanswered") =>
      client.post<{ status: string }>(
        `${org(orgId)}/conversations/${encodeURIComponent(id)}/unanswered`,
        { reason },
      ),
    listUnanswered: (orgId: string, chatbotId?: string) => {
      const query = chatbotId ? `?chatbot_id=${encodeURIComponent(chatbotId)}` : "";
      return client.get<{ data: UnansweredGroup[] }>(`${org(orgId)}/unanswered${query}`);
    },
    listKnowledgeGaps: (orgId: string, chatbotId?: string) => {
      const query = chatbotId ? `?chatbot_id=${encodeURIComponent(chatbotId)}` : "";
      return client.get<{ data: KnowledgeGap[] }>(`${org(orgId)}/knowledge-gaps${query}`);
    },
    getRetention: (orgId: string) =>
      client.get<RetentionSettings>(`${org(orgId)}/conversation-retention`),
    createConversationExport: (
      orgId: string,
      body: {
        chatbot_id?: string;
        channel?: string;
        from_at?: string;
        to_at?: string;
        status?: string;
      } = {},
    ) => client.post<ConversationExport>(`${org(orgId)}/conversations/exports`, body),
    downloadConversationExport: (orgId: string, exportId: string) =>
      client.download(`${org(orgId)}/exports/${encodeURIComponent(exportId)}/download`),
    analyticsSummary: (
      orgId: string,
      filters: { from?: string; to?: string; chatbot_id?: string; channel?: string } = {},
    ) => {
      const query = new URLSearchParams();
      if (filters.from) query.set("from", filters.from);
      if (filters.to) query.set("to", filters.to);
      if (filters.chatbot_id) query.set("chatbot_id", filters.chatbot_id);
      if (filters.channel) query.set("channel", filters.channel);
      const suffix = query.size ? `?${query.toString()}` : "";
      return client.get<AnalyticsSummary>(`${org(orgId)}/analytics/summary${suffix}`);
    },
    analyticsTimeseries: (
      orgId: string,
      metric: "conversations" | "resolved" | "tokens" | "cost",
      interval: "day" | "month",
      filters: { from?: string; to?: string; chatbot_id?: string; channel?: string } = {},
    ) => {
      const query = new URLSearchParams({ metric, interval });
      if (filters.from) query.set("from", filters.from);
      if (filters.to) query.set("to", filters.to);
      if (filters.chatbot_id) query.set("chatbot_id", filters.chatbot_id);
      if (filters.channel) query.set("channel", filters.channel);
      return client.get<Timeseries>(`${org(orgId)}/analytics/timeseries?${query.toString()}`);
    },
    // auth
    signup: (body: { email: string; password: string; name: string; org_name: string }) =>
      client.post<SignupResponse>("/auth/signup", body),
    login: (body: { email: string; password: string }) =>
      client.post<MeResponse>("/auth/login", body),
    logout: () => client.post<void>("/auth/logout"),
    verifyEmail: (token: string) =>
      client.post<{ status: string }>("/auth/verify-email", { token }),
    resendVerification: () => client.post<{ status: string }>("/auth/resend-verification"),
    forgotPassword: (email: string) =>
      client.post<{ status: string }>("/auth/forgot-password", { email }),
    resetPassword: (token: string, password: string) =>
      client.post<{ status: string }>("/auth/reset-password", { token, password }),

    // account
    me: () => client.get<MeResponse>("/me"),
    updateMe: (body: { name?: string }) => client.patch<User>("/me", body),
    changePassword: (body: { current_password: string; new_password: string }) =>
      client.post<void>("/me/password", body),
    listSessions: () => client.get<Page<SessionInfo>>("/me/sessions"),
    revokeSession: (id: string) => client.delete(`/me/sessions/${encodeURIComponent(id)}`),
    revokeOtherSessions: () => client.delete("/me/sessions"),

    // organizations
    listOrgs: () => client.get<Page<Org>>("/orgs"),
    createOrg: (name: string) => client.post<Org>("/orgs", { name }),
    getOrg: (orgId: string) => client.get<Org>(org(orgId)),
    updateOrg: (orgId: string, body: { name?: string; settings?: Record<string, unknown> }) =>
      client.patch<Org>(org(orgId), body),
    transferOwnership: (orgId: string, body: { new_owner_user_id: string; password: string }) =>
      client.post<Org>(`${org(orgId)}/transfer-ownership`, body),

    // members & invitations
    listMembers: (orgId: string) => client.get<Page<Member>>(`${org(orgId)}/members`),
    changeMemberRole: (orgId: string, membershipId: string, role: AssignableRole) =>
      client.patch<Member>(`${org(orgId)}/members/${encodeURIComponent(membershipId)}`, { role }),
    removeMember: (orgId: string, membershipId: string) =>
      client.delete(`${org(orgId)}/members/${encodeURIComponent(membershipId)}`),
    listInvitations: (orgId: string) => client.get<Page<Invitation>>(`${org(orgId)}/invitations`),
    invite: (orgId: string, body: { email: string; role: AssignableRole }) =>
      client.post<Invitation>(`${org(orgId)}/invitations`, body),
    resendInvitation: (orgId: string, id: string) =>
      client.post<Invitation>(`${org(orgId)}/invitations/${encodeURIComponent(id)}/resend`),
    revokeInvitation: (orgId: string, id: string) =>
      client.delete(`${org(orgId)}/invitations/${encodeURIComponent(id)}`),
    lookupInvitation: (token: string) =>
      client.get<InvitationPreview>(`/invitations/lookup?token=${encodeURIComponent(token)}`),
    acceptInvitation: (token: string) => client.post<OrgRole>("/invitations/accept", { token }),

    // chatbots
    chatbotOptions: (orgId: string) => client.get<ChatbotOptions>(`${org(orgId)}/chatbot-options`),
    listChatbots: (orgId: string, filters: { status?: ChatbotStatus | ""; q?: string } = {}) => {
      const query = new URLSearchParams();
      if (filters.status) query.set("status", filters.status);
      if (filters.q?.trim()) query.set("q", filters.q.trim());
      const suffix = query.size ? `?${query.toString()}` : "";
      return client.get<ChatbotList>(`${org(orgId)}/chatbots${suffix}`);
    },
    getChatbot: (orgId: string, id: string) =>
      client.get<Chatbot>(`${org(orgId)}/chatbots/${encodeURIComponent(id)}`),
    createChatbot: (orgId: string, body: CreateChatbotBody) =>
      client.post<Chatbot>(`${org(orgId)}/chatbots`, body),
    updateChatbot: (orgId: string, id: string, body: UpdateChatbotBody) =>
      client.patch<Chatbot>(`${org(orgId)}/chatbots/${encodeURIComponent(id)}`, body),
    deleteChatbot: (orgId: string, id: string) =>
      client.delete(`${org(orgId)}/chatbots/${encodeURIComponent(id)}`),
    rotateChatbotKey: (orgId: string, id: string) =>
      client.post<Chatbot>(`${org(orgId)}/chatbots/${encodeURIComponent(id)}/rotate-public-key`),

    // knowledge
    knowledgeLimits: (orgId: string, botId: string) =>
      client.get<UploadLimits>(`${bot(orgId, botId)}/knowledge/limits`),
    listDocuments: (
      orgId: string,
      botId: string,
      filters: { status?: DocumentStatus | ""; q?: string } = {},
    ) => {
      const query = new URLSearchParams();
      if (filters.status) query.set("status", filters.status);
      if (filters.q?.trim()) query.set("q", filters.q.trim());
      const suffix = query.size ? `?${query.toString()}` : "";
      return client.get<DocumentList>(`${bot(orgId, botId)}/documents${suffix}`);
    },
    uploadDocument: (orgId: string, botId: string, file: File) =>
      client.upload<KnowledgeDocument>(
        `${bot(orgId, botId)}/documents?filename=${encodeURIComponent(file.name)}`,
        file,
        file.type || "application/octet-stream",
      ),
    deleteDocument: (orgId: string, botId: string, id: string) =>
      client.delete(`${bot(orgId, botId)}/documents/${encodeURIComponent(id)}`),
    reprocessDocument: (orgId: string, botId: string, id: string) =>
      client.post<KnowledgeDocument>(
        `${bot(orgId, botId)}/documents/${encodeURIComponent(id)}/reprocess`,
      ),
    listChunks: (orgId: string, botId: string, id: string, offset = 0, limit = 10) =>
      client.get<{ data: ChunkPreview[]; total: number }>(
        `${bot(orgId, botId)}/documents/${encodeURIComponent(id)}/chunks?limit=${limit}&offset=${offset}`,
      ),
    reindex: (orgId: string, botId: string, force = false) =>
      client.post<{ queued: number; skipped: number; embedding_model: string }>(
        `${bot(orgId, botId)}/reindex${force ? "?force=true" : ""}`,
      ),
    listSources: (orgId: string, botId: string) =>
      client.get<Page<KnowledgeSource>>(`${bot(orgId, botId)}/sources`),
    createWebsite: (orgId: string, botId: string, body: WebsiteSourceBody) =>
      client.post<KnowledgeSource>(`${bot(orgId, botId)}/sources`, body),
    syncSource: (orgId: string, botId: string, id: string) =>
      client.post<KnowledgeSource>(`${bot(orgId, botId)}/sources/${encodeURIComponent(id)}/sync`),
    deleteSource: (orgId: string, botId: string, id: string) =>
      client.delete(`${bot(orgId, botId)}/sources/${encodeURIComponent(id)}`),
    searchKnowledge: (
      orgId: string,
      botId: string,
      body: { query: string; mode: SearchMode; top_k?: number },
    ) => client.post<SearchResponse>(`${bot(orgId, botId)}/retrieval/search`, body),

    // audit
    listAuditLogs: (orgId: string, cursor?: string | null) =>
      client.get<AuditPage>(
        `${org(orgId)}/audit-logs?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      ),
  };
}

export type Endpoints = ReturnType<typeof createEndpoints>;

export const api: Endpoints = createEndpoints(createApiClient({ baseUrl: publicApiBaseUrl() }));
