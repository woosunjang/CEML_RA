"use client";

import { useEffect, useMemo, useState } from "react";
import Sidebar from "@/components/Sidebar";
import {
  checkHealth,
  fetchResearchContextBundle,
  fetchResearchThreads,
  previewEvidenceCriticEnvelope,
  previewResearchLoop,
  ResearchContextBundle,
  ResearchLoopPacket,
  ResearchObjectPreview,
  ResearchThreadListItem,
  SubagentOutputEnvelope,
} from "@/lib/api";

function StateBadge({ value }: { value: string }) {
  const tone = value.includes("review") || value.includes("pending")
    ? "var(--warning)"
    : value.includes("preview") || value.includes("candidate")
      ? "var(--accent-light)"
      : "var(--success)";
  return (
    <span
      className="inline-flex min-w-0 items-center rounded-md px-2 py-0.5 text-[10px] font-semibold"
      style={{ background: `${tone}22`, color: tone }}
    >
      {value}
    </span>
  );
}

function ObjectRow({ item }: { item: ResearchObjectPreview }) {
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
      <div className="mb-2 flex min-w-0 flex-wrap items-center gap-2">
        <span className="truncate text-xs font-semibold text-[var(--text-primary)]">{item.object_ref}</span>
        <StateBadge value={item.section} />
        <StateBadge value={item.status || "unknown"} />
      </div>
      <p className="text-xs leading-relaxed text-[var(--text-secondary)]">{item.text}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <StateBadge value={item.authority_state || "authority_missing"} />
        <StateBadge value={item.review_state || "review_missing"} />
        <StateBadge value={item.support_state || "support_missing"} />
      </div>
    </div>
  );
}

function JsonPreview({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[280px] overflow-auto rounded-md border border-[var(--border)] bg-[var(--bg-primary)] p-3 text-[11px] leading-relaxed text-[var(--text-secondary)]">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export default function ResearchReviewPage() {
  const [online, setOnline] = useState(false);
  const [threads, setThreads] = useState<ResearchThreadListItem[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string>("");
  const [contextBundle, setContextBundle] = useState<ResearchContextBundle | null>(null);
  const [loopPacket, setLoopPacket] = useState<ResearchLoopPacket | null>(null);
  const [envelope, setEnvelope] = useState<SubagentOutputEnvelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      const isOnline = await checkHealth();
      setOnline(isOnline);
      if (!isOnline) {
        setLoading(false);
        return;
      }
      try {
        const data = await fetchResearchThreads();
        setThreads(data.threads);
        setSelectedThreadId((current) => current || data.threads[0]?.thread_id || "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "연구 thread를 불러오지 못했습니다.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  useEffect(() => {
    if (!selectedThreadId || !online) return;
    const loadReview = async () => {
      setLoading(true);
      setError(null);
      try {
        const [contextPayload, loopPayload] = await Promise.all([
          fetchResearchContextBundle(selectedThreadId),
          previewResearchLoop(selectedThreadId),
        ]);
        const envelopePayload = await previewEvidenceCriticEnvelope(loopPayload.packet);
        setContextBundle(contextPayload.bundle);
        setLoopPacket(loopPayload.packet);
        setEnvelope(envelopePayload.envelope);
      } catch (err) {
        setError(err instanceof Error ? err.message : "연구 리뷰 preview를 만들지 못했습니다.");
        setContextBundle(null);
        setLoopPacket(null);
        setEnvelope(null);
      } finally {
        setLoading(false);
      }
    };
    loadReview();
  }, [selectedThreadId, online]);

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.thread_id === selectedThreadId),
    [threads, selectedThreadId],
  );

  return (
    <div className="flex h-screen">
      <Sidebar serverOnline={online} />

      <main className="flex-1 overflow-hidden">
        <div className="flex h-full flex-col">
          <header className="border-b border-[var(--border)] px-5 py-4" style={{ background: "var(--bg-secondary)" }}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-bold text-[var(--text-primary)]">Research Thread Review</h1>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  context bundle · loop packet · critique gate · patch preview
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`status-dot ${online ? "status-online" : "status-offline"}`} />
                <span className="text-xs text-[var(--text-secondary)]">{online ? "read-only API" : "offline"}</span>
              </div>
            </div>
          </header>

          <div className="grid min-h-0 flex-1 grid-cols-[280px_1fr] overflow-hidden">
            <aside className="border-r border-[var(--border)] bg-[var(--bg-secondary)] p-3">
              <div className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                Threads
              </div>
              <div className="space-y-2">
                {threads.map((thread) => (
                  <button
                    key={thread.thread_id}
                    onClick={() => setSelectedThreadId(thread.thread_id)}
                    className="w-full rounded-md border p-3 text-left transition-colors"
                    style={{
                      borderColor: selectedThreadId === thread.thread_id ? "var(--accent-light)" : "var(--border)",
                      background: selectedThreadId === thread.thread_id ? "hsla(239,84%,67%,0.14)" : "var(--bg-elevated)",
                    }}
                  >
                    <div className="truncate text-sm font-semibold text-[var(--text-primary)]">{thread.topic}</div>
                    <div className="mt-1 truncate text-[11px] text-[var(--text-muted)]">{thread.research_state}</div>
                  </button>
                ))}
              </div>
            </aside>

            <section className="min-w-0 overflow-y-auto p-5">
              {loading && (
                <div className="grid gap-3">
                  <div className="skeleton h-20" />
                  <div className="skeleton h-40" />
                  <div className="skeleton h-40" />
                </div>
              )}

              {!loading && error && (
                <div className="rounded-md border border-[var(--error)] bg-[var(--bg-elevated)] p-4 text-sm text-[var(--text-primary)]">
                  {error}
                </div>
              )}

              {!loading && !error && selectedThread && contextBundle && loopPacket && envelope && (
                <div className="space-y-5">
                  <section className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h2 className="text-base font-semibold text-[var(--text-primary)]">{selectedThread.topic}</h2>
                        <p className="mt-1 text-xs text-[var(--text-muted)]">{selectedThread.thread_id}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <StateBadge value={selectedThread.research_state} />
                        <StateBadge value={`objects ${contextBundle.relevant_objects.length}`} />
                        <StateBadge value={`gaps ${contextBundle.evidence_gaps.length}`} />
                      </div>
                    </div>
                  </section>

                  <section className="grid gap-5 xl:grid-cols-2">
                    <div className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Relevant Objects</h3>
                      <div className="space-y-2">
                        {contextBundle.relevant_objects.slice(0, 8).map((item) => (
                          <ObjectRow key={`${item.section}-${item.id}`} item={item} />
                        ))}
                      </div>
                    </div>

                    <div className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Evidence Gaps</h3>
                      <div className="space-y-2">
                        {contextBundle.evidence_gaps.length === 0 ? (
                          <div className="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-3 text-xs text-[var(--text-muted)]">
                            evidence gap 없음
                          </div>
                        ) : (
                          contextBundle.evidence_gaps.slice(0, 8).map((item) => (
                            <ObjectRow key={`${item.section}-${item.id}`} item={item} />
                          ))
                        )}
                      </div>
                    </div>
                  </section>

                  <section className="grid gap-5 xl:grid-cols-3">
                    <div className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Selected Roles</h3>
                      <div className="space-y-2">
                        {loopPacket.selected_roles.map((role) => (
                          <div key={role.role} className="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                            <div className="text-xs font-semibold text-[var(--text-primary)]">{role.role}</div>
                            <div className="mt-1 text-[11px] leading-relaxed text-[var(--text-muted)]">{role.reason}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Critique Gate</h3>
                      <StateBadge value={envelope.critique_gate.status} />
                      <div className="mt-3 space-y-2">
                        {envelope.critique_gate.findings.map((finding) => (
                          <div key={finding.id} className="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                            <div className="text-[11px] font-semibold text-[var(--warning)]">{finding.status}</div>
                            <div className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{finding.text}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                      <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Activation Preview</h3>
                      <JsonPreview value={contextBundle.activation_previews} />
                    </div>
                  </section>

                  <section className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">Artifact Candidates</h3>
                      <StateBadge value={envelope.artifact_co_production.status} />
                    </div>
                    <div className="grid gap-2 xl:grid-cols-2">
                      {envelope.artifact_co_production.candidates.length === 0 ? (
                        <div className="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-3 text-xs text-[var(--text-muted)]">
                          artifact candidate 없음
                        </div>
                      ) : (
                        envelope.artifact_co_production.candidates.map((candidate) => (
                          <div key={candidate.id} className="rounded-md border border-[var(--border)] bg-[var(--bg-elevated)] p-3">
                            <div className="mb-2 flex flex-wrap items-center gap-2">
                              <span className="text-xs font-semibold text-[var(--text-primary)]">{candidate.id}</span>
                              <StateBadge value={candidate.status} />
                            </div>
                            <p className="text-xs leading-relaxed text-[var(--text-secondary)]">{candidate.text}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </section>

                  <section className="rounded-md border border-[var(--border)] bg-[var(--bg-secondary)] p-4">
                    <h3 className="mb-3 text-sm font-semibold text-[var(--text-primary)]">Recommended Patch Preview</h3>
                    <JsonPreview value={envelope.recommended_thread_patch} />
                  </section>
                </div>
              )}
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
