export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  agent_name?: string;
  citations?: Citation[];
  execution_steps?: ExecutionStep[];
  timestamp: string;
}

export interface Citation {
  number: number;
  title: string;
  source: string;
  document_type: string;
  score: number;
}

export interface ExecutionStep {
  agent: string;
  task: string;
  status: "pending" | "executing" | "completed" | "failed";
  error?: string;
}

export interface AgentInfo {
  name: string;
  display_name: string;
  description: string;
  icon: string;
  capabilities: string[];
  online: boolean;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  agent_override?: string;
  mode?: string;  // normal | debate | pipeline
  debate_rounds?: number;
  pipeline_id?: string;
  pipeline_vars?: Record<string, string>;
  filters?: Record<string, string>;
}

export interface ChatResponse {
  conversation_id: string;
  content: string;
  agent_name: string;
  citations: Citation[];
  execution_steps: ExecutionStep[];
  metadata: Record<string, unknown>;
}

export interface ScoutStats {
  total: number;
  analyzed: number;
  today: number;
  avg_score: number;
}

export interface ScoutPaper {
  id: string;
  title: string;
  authors: string;
  source: string;
  url: string;
  year: number;
  relevance_score: number;
  summary?: string;
  tags?: string[];
}

export interface Session {
  conversation_id: string;
  title: string;
  created_at: string;
  last_message_at: string;
  message_count: number;
}
