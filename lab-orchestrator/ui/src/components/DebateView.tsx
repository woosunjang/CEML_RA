"use client";

import { useState } from "react";

interface DebateRound {
  round: number;
  panelists: {
    name: string;
    content: string;
    elapsed?: number;
    status: "pending" | "running" | "done";
  }[];
}

interface DebateViewProps {
  rounds: DebateRound[];
  finalAnswer: string;
  elapsedTotal?: number;
  complexity?: number;
  isStreaming?: boolean;
}

const PANELIST_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  analyst: { icon: "🟢", color: "hsl(160, 72%, 47%)", label: "Analyst" },
  critic: { icon: "🟣", color: "hsl(270, 70%, 60%)", label: "Critic" },
  synthesizer: { icon: "🔵", color: "hsl(210, 80%, 55%)", label: "Synthesizer" },
};

export default function DebateView({
  rounds,
  finalAnswer,
  elapsedTotal,
  complexity,
  isStreaming,
}: DebateViewProps) {
  const [expandedRound, setExpandedRound] = useState<number | null>(null);

  return (
    <div className="space-y-3">
      {/* Debate Header */}
      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">🏛️</span>
        <span className="text-xs font-semibold" style={{ color: "hsl(270,70%,60%)" }}>
          Multi-LLM Debate
        </span>
        {elapsedTotal && (
          <span className="text-[10px] text-[var(--text-muted)]">
            {elapsedTotal.toFixed(1)}s
          </span>
        )}
        {complexity !== undefined && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full"
            style={{ background: "hsla(270,70%,60%,0.15)", color: "hsl(270,78%,68%)" }}>
            복잡도: {(complexity * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {/* Rounds */}
      {rounds.map((round) => (
        <div key={round.round} className="glass-light p-3">
          <button
            className="flex items-center justify-between w-full text-left"
            onClick={() => setExpandedRound(expandedRound === round.round ? null : round.round)}
          >
            <span className="text-xs font-semibold text-[var(--text-primary)]">
              라운드 {round.round}
            </span>
            <div className="flex items-center gap-2">
              {round.panelists.map((p) => {
                const cfg = PANELIST_CONFIG[p.name] || { icon: "⚪", color: "#888" };
                return (
                  <span key={p.name} className="flex items-center gap-1 text-[10px]">
                    <span>{cfg.icon}</span>
                    <span style={{ color: p.status === "done" ? cfg.color : "var(--text-muted)" }}>
                      {p.status === "done" ? "✓" : p.status === "running" ? "..." : "○"}
                    </span>
                  </span>
                );
              })}
              <span className="text-[10px] text-[var(--text-muted)]">
                {expandedRound === round.round ? "▲" : "▼"}
              </span>
            </div>
          </button>

          {expandedRound === round.round && (
            <div className="mt-3 space-y-2 animate-fade-in">
              {round.panelists.map((p) => {
                const cfg = PANELIST_CONFIG[p.name] || { icon: "⚪", color: "#888", label: p.name };
                return (
                  <div key={p.name} className="rounded-lg p-3"
                    style={{ background: "var(--bg-primary)", border: `1px solid ${cfg.color}20` }}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="flex items-center gap-1.5 text-xs font-medium"
                        style={{ color: cfg.color }}>
                        {cfg.icon} {cfg.label}
                      </span>
                      {p.elapsed && (
                        <span className="text-[10px] text-[var(--text-muted)]">
                          {p.elapsed.toFixed(1)}s
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                      {p.content || (p.status === "running" ? "응답 중..." : "대기 중")}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}

      {/* Streaming indicator */}
      {isStreaming && (
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <span className="animate-pulse">⚖️</span>
          <span>Judge 종합 중...</span>
        </div>
      )}
    </div>
  );
}
