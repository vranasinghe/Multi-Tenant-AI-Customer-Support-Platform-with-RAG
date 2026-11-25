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
    updateOrg: (orgId: string, body: { name?: string }) => client.patch<Org>(org(orgId), body),
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
