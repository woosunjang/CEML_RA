import { ChatRequest, ChatResponse, AgentInfo, Session } from "./types";

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

// ---- Research Thread Review ----

export interface ResearchThreadListItem {
  thread_id: string;
  topic: string;
  research_state: string;
  updated_at: string;
  json_path: string;
  markdown_path: string;
}

export interface ResearchObjectPreview {
  section: string;
  id: string;
  object_ref: string;
  text: string;
  status: string;
  authority_state: string;
  review_state: string;
  support_state: string;
  source_refs: string[];
  artifact_refs: string[];
  related_object_refs: string[];
}

export interface ResearchContextBundle {
  bundle_id: string;
  thread_id: string;
  topic: string;
  research_state: string;
  trigger: { type: string; summary: string };
  thread_summary: {
    section_counts: Record<string, number>;
    open_next_actions: ResearchObjectPreview[];
    recent_decisions: ResearchObjectPreview[];
  };
  relevant_objects: ResearchObjectPreview[];
  evidence_gaps: ResearchObjectPreview[];
  activation_previews: Record<string, unknown>;
  live_store_mutations: unknown[];
}

export interface ResearchLoopPacket {
  packet_id: string;
  thread_id: string;
  trigger: { type: string; summary: string };
  context_bundle: ResearchContextBundle;
  selected_roles: { role: string; reason: string; output: string; must_not: string }[];
  thread_patch_preview: Record<string, unknown>;
  live_store_mutations: unknown[];
}

export interface SubagentOutputEnvelope {
  envelope_id: string;
  thread_id: string;
  role: string;
  output_type: string;
  critique_gate: {
    status: string;
    findings: { id: string; status: string; text: string }[];
    live_store_mutations: unknown[];
  };
  artifact_co_production: {
    status: string;
    candidates: { id: string; status: string; text: string }[];
    live_store_mutations: unknown[];
  };
  recommended_thread_patch: Record<string, unknown>;
  live_store_mutations: unknown[];
}

export interface EvidenceMatrixRow {
  row_id: string;
  focus: ResearchObjectPreview;
  maturity_lane: { lane: string; source: string; note: string };
  current_evidence: ResearchObjectPreview[];
  counterarguments: ResearchObjectPreview[];
  missing_evidence: { id: string; status: string; text: string }[];
  review_questions: string[];
  recommended_review_action: { action: string; status: string; text: string };
  live_store_mutations: unknown[];
}

export interface ResearchEvidenceMatrix {
  matrix_id: string;
  thread_id: string;
  topic: string;
  trigger: { type: string; summary: string };
  review_surface_boundary: { kind: string; text: string };
  rows: EvidenceMatrixRow[];
  coverage: {
    row_count: number;
    rows_with_evidence: number;
    rows_with_counterarguments: number;
    rows_with_missing_evidence: number;
    maturity_lane_counts: Record<string, number>;
    critique_gate: string;
    live_store_mutations: unknown[];
  };
  recommended_thread_patch: Record<string, unknown>;
  live_store_mutations: unknown[];
}

export interface ResearchPatchReviewRecord {
  schema_version: number;
  review_id: string;
  thread_id: string;
  action: "preview" | "apply" | "reject";
  patch_hash: string;
  reviewer: string;
  review_note: string;
  result_status: string;
  created_at: string;
  artifact_mutations: { type: string; path: string }[];
  live_store_mutations: unknown[];
}

export interface ResearchPatchReviewResponse {
  schema_version: number;
  status: string;
  dry_run: boolean;
  read_only: boolean;
  artifact_write: boolean;
  thread_id: string;
  action: "preview" | "apply" | "reject";
  patch_hash: string;
  patch_result: {
    status: string;
    changes?: unknown;
    preview_markdown?: string;
    live_store_mutations?: unknown[];
  };
  review_record: ResearchPatchReviewRecord;
  review_record_path: string | null;
  artifact_mutations: { type: string; path: string }[];
  live_store_mutations: unknown[];
}

export async function fetchResearchThreads(): Promise<{
  threads: ResearchThreadListItem[];
  count: number;
  read_only: boolean;
}> {
  const res = await fetch(`${API_BASE}/research/threads`);
  if (!res.ok) throw new Error("Failed to fetch research threads");
  return res.json();
}

export async function fetchResearchContextBundle(threadId: string): Promise<{
  bundle: ResearchContextBundle;
  read_only: boolean;
  dry_run: boolean;
  live_store_mutations: unknown[];
}> {
  const params = new URLSearchParams({
    trigger_type: "on_demand",
    trigger_summary: "UI research review",
  });
  const res = await fetch(`${API_BASE}/research/threads/${encodeURIComponent(threadId)}/context?${params}`);
  if (!res.ok) throw new Error("Failed to fetch research context bundle");
  return res.json();
}

export async function previewResearchLoop(threadId: string): Promise<{
  packet: ResearchLoopPacket;
  read_only: boolean;
  dry_run: boolean;
  live_store_mutations: unknown[];
}> {
  const res = await fetch(`${API_BASE}/research/loops/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      thread_id: threadId,
      trigger_type: "on_demand",
      trigger_summary: "UI research review",
    }),
  });
  if (!res.ok) throw new Error("Failed to preview research loop");
  return res.json();
}

export async function previewEvidenceCriticEnvelope(packet: ResearchLoopPacket): Promise<{
  envelope: SubagentOutputEnvelope;
  read_only: boolean;
  dry_run: boolean;
  live_store_mutations: unknown[];
}> {
  const res = await fetch(`${API_BASE}/research/subagent-envelopes/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      loop_packet: packet,
      role: "Evidence Critic",
      output_type: "evidence_boundary_preview",
      summary: "UI review surface에서 근거 경계와 승격 금지 조건을 확인한다.",
      missing_evidence: ["UI preview는 source text를 직접 검증하지 않으므로 claim 승격 전에 근거 확인이 필요하다."],
      counterarguments: ["Review surface 표시만으로 연구 품질이 검증되었다고 볼 수 없다."],
      failure_modes: ["preview를 approval이나 live ingest로 오해하면 실패한다."],
      artifact_candidates: ["UI 검토용 research-thread review note 후보"],
    }),
  });
  if (!res.ok) throw new Error("Failed to preview evidence critic envelope");
  return res.json();
}

export async function previewResearchEvidenceMatrix(threadId: string): Promise<{
  matrix: ResearchEvidenceMatrix;
  recommended_thread_patch: Record<string, unknown>;
  read_only: boolean;
  dry_run: boolean;
  live_store_mutations: unknown[];
}> {
  const res = await fetch(`${API_BASE}/research/threads/${encodeURIComponent(threadId)}/evidence-matrix/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      trigger_type: "on_demand",
      trigger_summary: "UI evidence matrix review",
    }),
  });
  if (!res.ok) throw new Error("Failed to preview evidence matrix");
  return res.json();
}

async function researchPatchReviewRequest(
  threadId: string,
  action: "preview" | "apply" | "reject",
  patch: Record<string, unknown>,
  options: { reviewer?: string; review_note?: string; confirm_artifact_write?: boolean } = {},
): Promise<ResearchPatchReviewResponse> {
  const res = await fetch(`${API_BASE}/research/threads/${encodeURIComponent(threadId)}/patches/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      patch,
      reviewer: options.reviewer || "ui_research_review",
      review_note: options.review_note || "",
      confirm_artifact_write: options.confirm_artifact_write === true,
    }),
  });
  if (!res.ok) {
    let detail = `Failed to ${action} research patch`;
    try {
      const payload = await res.json();
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch { /* keep default */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function previewResearchThreadPatch(
  threadId: string,
  patch: Record<string, unknown>,
): Promise<ResearchPatchReviewResponse> {
  return researchPatchReviewRequest(threadId, "preview", patch);
}

export async function applyResearchThreadPatch(
  threadId: string,
  patch: Record<string, unknown>,
): Promise<ResearchPatchReviewResponse> {
  return researchPatchReviewRequest(threadId, "apply", patch, {
    confirm_artifact_write: true,
    review_note: "UI에서 patch 적용을 승인했다.",
  });
}

export async function rejectResearchThreadPatch(
  threadId: string,
  patch: Record<string, unknown>,
): Promise<ResearchPatchReviewResponse> {
  return researchPatchReviewRequest(threadId, "reject", patch, {
    confirm_artifact_write: true,
    review_note: "UI에서 patch 후보를 거절했다.",
  });
}
