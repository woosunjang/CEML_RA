"use client";

import { useState, useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import {
  checkHealth,
  fetchAgents,
  fetchDebateStatus,
  fetchModelProfiles,
  switchModelProfile,
} from "@/lib/api";
import { AgentInfo } from "@/lib/types";

const AGENT_ICONS: Record<string, string> = {
  literature: "📚",
  teaching: "🎓",
  writing: "✍️",
  presentation: "📽️",
  project: "📋",
};

const AGENT_COLORS: Record<string, string> = {
  literature: "hsl(239, 84%, 67%)",
  teaching: "hsl(160, 72%, 47%)",
  writing: "hsl(38, 92%, 65%)",
  presentation: "hsl(330, 70%, 60%)",
  project: "hsl(187, 92%, 41%)",
};

export default function DashboardPage() {
  const [online, setOnline] = useState(false);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [debate, setDebate] = useState<{ enabled: boolean; panelists: { name: string; model: string; provider: string }[]; rounds: number } | null>(null);
  const [profile, setProfile] = useState<string>("performance");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const isOnline = await checkHealth();
      setOnline(isOnline);
      if (!isOnline) { setLoading(false); return; }
      try {
        const [agentsData, debateData, profileData] = await Promise.all([
          fetchAgents(),
          fetchDebateStatus(),
          fetchModelProfiles(),
        ]);
        setAgents(agentsData.agents);
        setDebate(debateData);
        setProfile(profileData.active_profile);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleProfileSwitch = async () => {
    const next = profile === "performance" ? "cost" : "performance";
    try {
      await switchModelProfile(next);
      setProfile(next);
    } catch (e) { console.error(e); }
  };

  return (
    <div className="flex h-screen">
      <Sidebar serverOnline={online} />

      <main className="flex-1 overflow-y-auto p-6 lg:p-8">
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[var(--text-primary)]">
                대시보드
              </h1>
              <p className="text-sm text-[var(--text-muted)] mt-1">
                시스템 현황 및 에이전트 상태
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className={`status-dot ${online ? "status-online" : "status-offline"}`} />
              <span className="text-sm text-[var(--text-secondary)]">
                {online ? "정상 운영" : "서버 오프라인"}
              </span>
            </div>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-28 rounded-[var(--radius-lg)]" />
              ))}
            </div>
          ) : (
            <>
              {/* Stat Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Agents */}
                <div className="stat-card">
                  <div className="text-sm text-[var(--text-muted)] mb-2">에이전트</div>
                  <div className="text-3xl font-bold text-[var(--text-primary)]">
                    {agents.filter((a) => a.online).length}
                    <span className="text-lg text-[var(--text-muted)] font-normal">/{agents.length}</span>
                  </div>
                  <div className="text-xs text-[var(--success)] mt-1">활성</div>
                </div>

                {/* Debate */}
                <div className="stat-card">
                  <div className="text-sm text-[var(--text-muted)] mb-2">Debate Engine</div>
                  <div className="text-3xl font-bold text-[var(--text-primary)]">
                    {debate?.enabled ? "ON" : "OFF"}
                  </div>
                  <div className="text-xs text-[var(--text-secondary)] mt-1">
                    {debate?.panelists.length || 0}명 패널리스트 · {debate?.rounds || 3}라운드
                  </div>
                </div>

                {/* Model Profile */}
                <div className="stat-card cursor-pointer" onClick={handleProfileSwitch}>
                  <div className="text-sm text-[var(--text-muted)] mb-2">모델 프로필</div>
                  <div className="text-3xl font-bold text-[var(--text-primary)]">
                    {profile === "performance" ? "🚀" : "💰"}
                  </div>
                  <div className="text-xs text-[var(--accent-light)] mt-1">
                    {profile === "performance" ? "성능 모드" : "가성비 모드"}
                    <span className="text-[var(--text-muted)]"> · 클릭하여 전환</span>
                  </div>
                </div>
              </div>

              {/* Agent Grid */}
              <div>
                <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
                  에이전트 상태
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {agents.map((agent) => (
                    <div
                      key={agent.name}
                      className="glass glass-hover p-4 cursor-pointer"
                      onClick={() => window.location.href = `/?agent=${agent.name}`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <span className="text-2xl">{AGENT_ICONS[agent.name] || "🤖"}</span>
                          <div>
                            <div className="font-semibold text-sm text-[var(--text-primary)]">
                              {agent.display_name}
                            </div>
                            <div className="text-xs text-[var(--text-muted)]">
                              {agent.description}
                            </div>
                          </div>
                        </div>
                        <span className={`status-dot ${agent.online ? "status-online" : "status-offline"}`} />
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {agent.capabilities.slice(0, 3).map((cap) => (
                          <span
                            key={cap}
                            className="px-2 py-0.5 rounded-full text-[10px]"
                            style={{
                              background: `${AGENT_COLORS[agent.name]}15`,
                              color: AGENT_COLORS[agent.name],
                            }}
                          >
                            {cap}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Debate Panelists */}
              {debate?.enabled && (
                <div>
                  <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
                    🏛️ Debate Engine 패널리스트
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {debate.panelists.map((p) => (
                      <div key={p.name} className="glass p-4">
                        <div className="font-semibold text-sm text-[var(--text-primary)] capitalize mb-1">
                          {p.name === "analyst" ? "🟢" : p.name === "critic" ? "🟣" : "🔵"} {p.name}
                        </div>
                        <div className="text-xs text-[var(--text-secondary)]">{p.model}</div>
                        <div className="text-[10px] text-[var(--text-muted)] mt-1">{p.provider}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
