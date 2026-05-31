import { ChatRequest, ChatResponse, AgentInfo, Session, Message } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function sendChat(request: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    throw new Error(`Chat request failed: ${res.statusText}`);
  }

  return res.json();
}

export interface StreamCallbacks {
  onPlan?: (data: { tasks: { agent: string; task: string }[]; reasoning: string; conversation_id: string }) => void;
  onStep?: (data: { agent: string; index: number; status: string; error?: string }) => void;
  onAgent?: (data: { name: string }) => void;
  onToken?: (data: { text: string }) => void;
  onCitations?: (data: { citations: unknown[] }) => void;
  onDone?: (data: { conversation_id: string; agent_name: string; metadata: Record<string, unknown> }) => void;
  onError?: (error: Error) => void;
}

export async function sendChatStream(request: ChatRequest, callbacks: StreamCallbacks): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream request failed: ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let eventType = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ") && eventType) {
        try {
          const data = JSON.parse(line.slice(6));
          switch (eventType) {
            case "plan": callbacks.onPlan?.(data); break;
            case "step": callbacks.onStep?.(data); break;
            case "agent": callbacks.onAgent?.(data); break;
            case "token": callbacks.onToken?.(data); break;
            case "citations": callbacks.onCitations?.(data); break;
            case "done": callbacks.onDone?.(data); break;
          }
        } catch { /* skip malformed */ }
        eventType = "";
      }
    }
  }
}

export async function fetchAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await fetch(`${API_BASE}/agents`);
  if (!res.ok) {
    throw new Error(`Failed to fetch agents: ${res.statusText}`);
  }
  return res.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchDebateStatus(): Promise<{
  enabled: boolean;
  panelists: { name: string; model: string; provider: string }[];
  rounds: number;
}> {
  const res = await fetch(`${API_BASE}/debate/status`);
  if (!res.ok) throw new Error("Failed to fetch debate status");
  return res.json();
}

export async function fetchModelProfiles(): Promise<{
  active_profile: string;
  agents: Record<string, { model: string; model_heavy: string }>;
}> {
  const res = await fetch(`${API_BASE}/models/profiles`);
  if (!res.ok) throw new Error("Failed to fetch model profiles");
  return res.json();
}

export async function switchModelProfile(profile: string, agent?: string): Promise<unknown> {
  const res = await fetch(`${API_BASE}/models/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile, agent }),
  });
  if (!res.ok) throw new Error("Failed to switch profile");
  return res.json();
}

export interface GraphNode {
  id: string;
  summary: string;
  group: string;
  degree: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  fact: string;
}

export async function fetchGraphData(limit: number = 100): Promise<{
  nodes: GraphNode[];
  edges: GraphEdge[];
}> {
  const res = await fetch(`${API_BASE}/memory/graph?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch graph data");
  return res.json();
}

export async function searchMemory(query: string, limit: number = 5): Promise<{
  query: string;
  results: { fact: string; created_at: string | null; uuid: string | null; score: number | null }[];
  count: number;
}> {
  const res = await fetch(`${API_BASE}/memory/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  if (!res.ok) throw new Error("Failed to search memory");
  return res.json();
}

// ---- Session / Conversation History ----

export async function fetchSessions(): Promise<{ sessions: Session[] }> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function fetchSessionMessages(conversationId: string): Promise<{
  conversation_id: string;
  messages: { role: string; content: string; timestamp?: string; agent_name?: string }[];
}> {
  const res = await fetch(`${API_BASE}/sessions/${conversationId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch session messages");
  return res.json();
}

export async function deleteSession(conversationId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${conversationId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete session");
}
