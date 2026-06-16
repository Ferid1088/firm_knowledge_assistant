// Mirrors src/api.py response models. Backend is the source of truth.

export type Claim = {
  text: string;
  source: number;
  quote: string;
  verified: boolean;
};

export type Box = [number, number, number, number];

export type ArtifactChunk = {
  source: number;
  chunk_id: string;
  text: string;
  quote: string;
  address: {
    doc_id: string;
    page: number | null;
    heading_path: string[];
    boxes: Record<string, Box[]>;
  };
};

export type ChatResponse = {
  answer: string;
  answer_lang: string;
  confidence: number;
  attempts: number;
  claims: Claim[];
  artifact_chunks: ArtifactChunk[];
};

export type IngestJobStatus = {
  job_id: string;
  status: "queued" | "running" | "done" | "error";
  doc_id: string;
  n_chunks: number | null;
  doc_type: string | null;
  doc_type_confidence: number | null;
  parser_name: string | null;
  chunker_name: string | null;
  is_scanned: boolean | null;
  error: string | null;
};

export type DocumentType = {
  id: string;
  name: string;
  code: string;
  description: string;
  status: "active" | "archived";
  created_at: string;
};

export type User = {
  id: string;
  username: string;
  name: string;
  role_id: string;
  role_name: string;
  department_id: string;
  permissions: string[];
  must_change_password?: boolean;
  allowed_doc_type_ids?: string[] | null;
};

export type AuthStatus =
  | { setup_required: true }
  | { authenticated: false }
  | { authenticated: true; user: User };

export type AdminUser = {
  id: string;
  username: string;
  name: string;
  department_id: string;
  role_id: string;
  role_name: string;
  is_active: number;
  must_change_password: number;
  created_at: string;
  updated_at: string;
};

export type Department = {
  id: string;
  name: string;
  code: string;
  status: "active" | "archived";
  created_at: string;
};

export type Role = {
  id: string;
  name: string;
  description: string;
  is_system: number;
  created_at: string;
  permissions: string[];
};

export type Permission = {
  id: string;
  resource: string;
  action: string;
  description: string;
};

export type ConversationSummary = {
  id: string;
  title: string;
  status: "draft" | "active" | "archived" | "deleted";
  owner_user_id: string;
  department_id: string;
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  lang: string;
  claims: Claim[];
  artifact_chunks: ArtifactChunk[];
  created_at: string;
  integrity_verified: boolean;
};

export type ConversationDetail = ConversationSummary & {
  messages: ConversationMessage[];
  shares: { conversation_id: string; user_id: string; permission: string }[];
};
