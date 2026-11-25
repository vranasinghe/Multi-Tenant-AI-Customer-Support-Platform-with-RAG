/** Hand-written mirrors of the API contracts (services/api/app/schemas). Replaced by generated
 * OpenAPI types once the client generation lands (ADR-021). */

export type Role = "owner" | "admin" | "agent" | "viewer";
export type AssignableRole = Exclude<Role, "owner">;

export interface User {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
  locale: string;
}

export interface OrgRole {
  id: string;
  name: string;
  role: Role;
}

export interface MeResponse {
  user: User;
  orgs: OrgRole[];
}

export interface SignupResponse {
  user: User;
  org: OrgRole;
}

export interface Org {
  id: string;
  name: string;
  slug: string;
  status: string;
  role: Role;
  permissions: string[];
  settings: Record<string, unknown>;
  created_at: string;
}

export interface Member {
  id: string;
  user: { id: string; name: string; email: string; email_verified: boolean };
  role: Role;
  created_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: AssignableRole;
  status: "pending" | "expired";
  expires_at: string;
  created_at: string;
}

export interface InvitationPreview {
  org_name: string;
  inviter_name: string | null;
  role: AssignableRole;
  email_hint: string;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string | null;
  current: boolean;
}

export interface AuditEntry {
  id: string;
  action: string;
  actor: { id: string; name: string } | null;
  actor_type: string;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
  request_id: string | null;
  created_at: string;
}

export interface Page<T> {
  data: T[];
}

export interface AuditPage extends Page<AuditEntry> {
  next_cursor: string | null;
  has_more: boolean;
}

// ---------------------------------------------------------------------------------- chatbots

export type ChatbotStatus = "draft" | "active" | "paused" | "archived";
export type ChatbotTone = "professional" | "friendly" | "concise" | "custom";
export type ResponseLength = "concise" | "balanced" | "detailed";
export type LanguageMode = "auto" | "fixed";
export type WidgetPosition = "bottom-right" | "bottom-left";

export interface WidgetSettings {
  primary_color: string;
  accent_color: string;
  avatar_url: string | null;
  position: WidgetPosition;
  launcher_label: string;
  show_branding: boolean;
}

/** Everything a client may set on a chatbot (mirrors CreateChatbotRequest). */
export interface ChatbotConfig {
  name: string;
  description: string;
  instructions: string;
  tone: ChatbotTone;
  response_length: ResponseLength;
  welcome_message: string;
  fallback_message: string;
  language_mode: LanguageMode;
  language: string | null;
  model: string;
  temperature: number;
  max_output_tokens: number;
  strict_grounding: boolean;
  show_sources: boolean;
  retrieval_top_k: number;
  widget_settings: WidgetSettings;
}

export interface Chatbot extends ChatbotConfig {
  id: string;
  status: ChatbotStatus;
  public_key: string;
  created_by: { id: string; name: string } | null;
  created_at: string;
  updated_at: string;
}

export interface ChatbotList extends Page<Chatbot> {
  limit: number;
}

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  description: string;
  max_output_tokens: number;
  tier: string;
  default: boolean;
}

export interface ChatbotOptions {
  models: ModelOption[];
  languages: { code: string; label: string }[];
  tones: ChatbotTone[];
  response_lengths: ResponseLength[];
  statuses: ChatbotStatus[];
  chatbot_limit: number;
}

export type CreateChatbotBody = Partial<ChatbotConfig> & {
  name: string;
  status?: "draft" | "active";
};

export type UpdateChatbotBody = Partial<Omit<ChatbotConfig, "widget_settings">> & {
  status?: ChatbotStatus;
  widget_settings?: Partial<WidgetSettings>;
};

// ------------------------------------------------------------------------------- knowledge

export type DocumentStatus = "queued" | "processing" | "ready" | "failed";
export type SourceStatus = "pending" | "syncing" | "ready" | "partial" | "failed";
export type SearchMode = "vector" | "keyword" | "hybrid";

export interface IngestionJob {
  id: string;
  kind: "process_document" | "crawl";
  status: "queued" | "processing" | "succeeded" | "failed";
  stage: string | null;
  attempt: number;
  max_attempts: number;
  error_code: string | null;
  stats: Record<string, unknown>;
  queued_at: string;
  finished_at: string | null;
}

export interface KnowledgeDocument {
  id: string;
  source_id: string;
  title: string;
  uri: string;
  mime_type: string | null;
  size_bytes: number;
  status: DocumentStatus;
  error_code: string | null;
  error_message: string | null;
  page_count: number | null;
  chunk_count: number;
  token_count: number | null;
  version: number;
  embedding_model: string | null;
  needs_reindex: boolean;
  job: IngestionJob | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentList {
  data: KnowledgeDocument[];
  embedding_model: string;
}

export interface KnowledgeSource {
  id: string;
  kind: "file" | "website";
  name: string;
  status: SourceStatus;
  config: Record<string, unknown>;
  stats: Record<string, unknown>;
  last_synced_at: string | null;
  created_at: string;
  job: IngestionJob | null;
}

export interface ChunkPreview {
  id: string;
  ordinal: number;
  content: string;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  token_count: number;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  source_id: string;
  document_title: string;
  uri: string;
  ordinal: number;
  content: string;
  heading_path: string[];
  page_start: number | null;
  page_end: number | null;
  score: number;
  vector_score: number;
  vector_rank: number | null;
  keyword_rank: number | null;
}

export interface SearchResponse {
  results: SearchResult[];
  mode: SearchMode;
  embedding_model: string;
  took_ms: number;
}

export interface UploadLimits {
  max_bytes: number;
  extensions: string[];
  max_documents: number;
  max_pages_per_crawl: number;
}

export interface WebsiteSourceBody {
  url: string;
  name?: string;
  max_pages: number;
  max_depth: number;
  include: string[];
  exclude: string[];
  confirm_authorized: true;
}
