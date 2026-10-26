export type User = {
  id: string;
  name: string;
  email: string;
  role: "requester" | "engineer" | "admin";
};
export type Ticket = {
  id: string;
  number: string;
  owner_id: string;
  owner_name: string;
  assignee_id: string | null;
  assignee_name: string | null;
  title: string;
  description: string;
  priority: string;
  category: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  comments?: {
    id: string;
    content: string;
    author_name: string;
    created_at: string;
  }[];
  events?: {
    id: string;
    action: string;
    detail: string;
    actor_name: string;
    created_at: string;
  }[];
};
export type Source = {
  document_id: string;
  chunk_id: string;
  title: string;
  heading: string;
  product: string;
  version: string;
  source: string;
  content: string;
  score: number;
  citation: number;
};
export type Trace = {
  name: string;
  duration_ms: number;
  status: string;
  input: Record<string, unknown>;
};
export type Draft = {
  id: string;
  title: string;
  description: string;
  priority: string;
  category: string;
  status: string;
  conversation_id: string | null;
  created_at: string;
};
export type Message = {
  id: string;
  role: string;
  content: string;
  created_at?: string;
  metadata?: {
    sources?: Source[];
    traces?: Trace[];
    draft?: Draft | null;
    mode?: string;
    duration_ms?: number;
  };
};
export type Conversation = { id: string; title: string; updated_at: string };
export type Document = {
  id: string;
  title: string;
  product: string;
  version: string;
  source: string;
  characters: number;
  created_at: string;
  content?: string;
};
export type Dashboard = {
  total: number;
  counts: Record<string, number>;
  urgent: number;
  knowledge_count: number;
  recent_tickets: Ticket[];
  agent: {
    mode: string;
    runs: number;
    success_rate: number | null;
    avg_duration_ms: number;
    tool_calls: number;
  };
};
export type Run = {
  id: string;
  conversation_id: string;
  status: string;
  mode: string;
  duration_ms: number;
  tool_count: number;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
  created_at: string;
};
