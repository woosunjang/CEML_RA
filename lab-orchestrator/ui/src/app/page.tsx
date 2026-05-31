"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Message, AgentInfo, Citation, Session } from "@/lib/types";
import { sendChatStream, fetchAgents, checkHealth, switchModelProfile, fetchModelProfiles, fetchSessions, fetchSessionMessages, deleteSession } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import DebateView from "@/components/DebateView";

const AGENT_COLORS: Record<string, string> = {
  literature: "hsl(239, 84%, 67%)",
  teaching: "hsl(160, 72%, 47%)",
  writing: "hsl(38, 92%, 65%)",
  presentation: "hsl(330, 70%, 60%)",
  project: "hsl(187, 92%, 41%)",
  orchestrator: "hsl(270, 70%, 60%)",
  debate: "hsl(270, 70%, 60%)",
  pipeline: "hsl(200, 80%, 55%)",
  system: "hsl(220, 10%, 45%)",
};

const AGENT_ICONS: Record<string, string> = {
  literature: "📚", teaching: "🎓", writing: "✍️",
  presentation: "📽️", project: "📋", orchestrator: "🤖",
  debate: "🏛️", pipeline: "🔗", system: "⚙️",
};

interface StepStatus {
  agent: string;
  status: "pending" | "executing" | "completed" | "failed";
  error?: string;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string>("auto");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [serverOnline, setServerOnline] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingAgent, setStreamingAgent] = useState("");
  const [steps, setSteps] = useState<StepStatus[]>([]);
  const [debateMode, setDebateMode] = useState(false);
  const [modelProfile, setModelProfile] = useState("performance");
  const [toast, setToast] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const init = async () => {
      const online = await checkHealth();
      setServerOnline(online);
      if (online) {
        try {
          const [agentsData, profileData, sessionsData] = await Promise.all([
            fetchAgents(),
            fetchModelProfiles(),
            fetchSessions(),
          ]);
          setAgents(agentsData.agents);
          setModelProfile(profileData.active_profile);
          setSessions(sessionsData.sessions);
        } catch (e) { console.error(e); }
      }
    };
    init();
    const interval = setInterval(init, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.style.height = Math.min(inputRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleProfileToggle = async () => {
    const next = modelProfile === "performance" ? "cost" : "performance";
    try {
      await switchModelProfile(next);
      setModelProfile(next);
      showToast(`모델 프로필: ${next === "performance" ? "🚀 성능" : "💰 가성비"} 모드`);
    } catch { showToast("프로필 전환 실패"); }
  };

  const handleSend = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    setStreamingContent("");
    setStreamingAgent("");
    setSteps([]);

    let fullContent = "";
    let finalAgent = "";
    let finalCitations: Citation[] = [];

    try {
      await sendChatStream(
        {
          message: userMessage.content,
          conversation_id: conversationId,
          agent_override: selectedAgent === "auto" ? undefined : selectedAgent,
          mode: debateMode ? "debate" : "normal",
        },
        {
          onPlan: (data) => {
            setConversationId(data.conversation_id);
            setSteps(data.tasks.map((t) => ({ agent: t.agent, status: "pending" })));
          },
          onStep: (data) => {
            setSteps((prev) =>
              prev.map((s, i) =>
                i === data.index ? { ...s, status: data.status as StepStatus["status"], error: data.error } : s
              )
            );
          },
          onAgent: (data) => {
            finalAgent = data.name;
            setStreamingAgent(data.name);
          },
          onToken: (data) => {
            fullContent += data.text;
            setStreamingContent((prev) => prev + data.text);
          },
          onCitations: (data) => {
            finalCitations = data.citations as Citation[];
          },
          onDone: (data) => {
            setConversationId(data.conversation_id);
            finalAgent = data.agent_name;
          },
          onError: (error) => {
            fullContent = `❌ 오류: ${error.message}`;
          },
        }
      );
    } catch (error) {
      fullContent = `❌ 연결 오류: ${error instanceof Error ? error.message : "Unknown"}`;
      finalAgent = "system";
    }

    const assistantMessage: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: fullContent,
      agent_name: finalAgent,
      citations: finalCitations,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, assistantMessage]);
    setStreamingContent("");
    setStreamingAgent("");
    setSteps([]);
    setLoading(false);
    refreshSessions();
  }, [input, loading, conversationId, selectedAgent, debateMode]);

  const refreshSessions = useCallback(async () => {
    try {
      const data = await fetchSessions();
      setSessions(data.sessions);
    } catch { /* ignore */ }
  }, []);

  const handleNewChat = () => {
    setMessages([]);
    setConversationId(undefined);
    setSteps([]);
    setStreamingContent("");
    setStreamingAgent("");
  };

  const handleSelectSession = useCallback(async (sessionId: string) => {
    if (sessionId === conversationId) return;
    try {
      const data = await fetchSessionMessages(sessionId);
      const restored: Message[] = data.messages.map((m, i) => ({
        id: `restored-${i}`,
        role: m.role as "user" | "assistant",
        content: m.content,
        agent_name: m.agent_name,
        timestamp: m.timestamp || new Date().toISOString(),
      }));
      setMessages(restored);
      setConversationId(sessionId);
      setSteps([]);
      setStreamingContent("");
      setStreamingAgent("");
    } catch (e) {
      console.error("Failed to load session:", e);
      showToast("대화를 불러올 수 없습니다");
    }
  }, [conversationId]);

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.conversation_id !== sessionId));
      if (sessionId === conversationId) {
        handleNewChat();
      }
      showToast("대화가 삭제되었습니다");
    } catch {
      showToast("삭제 실패");
    }
  }, [conversationId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-screen">
      <Sidebar
        serverOnline={serverOnline}
        sessions={sessions}
        activeSessionId={conversationId}
        onSelectSession={handleSelectSession}
        onNewConversation={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border)]"
          style={{ background: "var(--bg-secondary)" }}>
          <div className="flex items-center gap-2 overflow-x-auto flex-1">
            <button onClick={handleNewChat}
              className="px-3 py-1.5 rounded-lg text-xs font-medium shrink-0 transition-all"
              style={{ background: "hsla(239,84%,67%,0.12)", color: "var(--accent-light)" }}>
              + 새 대화
            </button>
            <div className="w-px h-5 bg-[var(--border)] mx-1 shrink-0" />

            {/* Agent Pills */}
            <button onClick={() => setSelectedAgent("auto")}
              className="px-3 py-1.5 rounded-full text-xs font-medium shrink-0 transition-all"
              style={{
                background: selectedAgent === "auto" ? "hsla(270,70%,60%,0.12)" : "transparent",
                color: selectedAgent === "auto" ? "hsl(270,78%,68%)" : "var(--text-muted)",
              }}>
              🤖 Auto
            </button>
            {agents.map((agent) => (
              <button key={agent.name}
                onClick={() => setSelectedAgent(agent.name)}
                className="px-3 py-1.5 rounded-full text-xs font-medium shrink-0 transition-all"
                style={{
                  background: selectedAgent === agent.name ? `${AGENT_COLORS[agent.name]}18` : "transparent",
                  color: selectedAgent === agent.name ? AGENT_COLORS[agent.name] : "var(--text-muted)",
                }}>
                {agent.icon} {agent.display_name}
              </button>
            ))}
          </div>

          {/* Right: Profile Toggle */}
          <button onClick={handleProfileToggle}
            className="ml-3 px-2.5 py-1 rounded-lg text-[10px] font-medium shrink-0 transition-all"
            style={{
              background: modelProfile === "performance" ? "hsla(160,72%,47%,0.12)" : "hsla(38,92%,65%,0.12)",
              color: modelProfile === "performance" ? "hsl(160,80%,55%)" : "hsl(38,95%,70%)",
            }}>
            {modelProfile === "performance" ? "🚀 성능" : "💰 가성비"}
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
          {messages.length === 0 && !loading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-lg px-4">
                <div className="text-6xl sm:text-7xl mb-6 animate-float">🧠</div>
                <h2 className="text-2xl sm:text-3xl font-bold mb-3 bg-clip-text text-transparent"
                  style={{ backgroundImage: "var(--gradient-brand)" }}>
                  CEML Research Assistant
                </h2>
                <p className="text-[var(--text-muted)] mb-8 text-sm">
                  멀티 에이전트 연구 보조 시스템
                </p>
                <div className="flex gap-2 justify-center flex-wrap">
                  {[
                    "NASICON 최신 논문 동향 분석",
                    "고체전해질 세미나 강의안",
                    "연구 제안서 배경 작성",
                  ].map((q) => (
                    <button key={q} onClick={() => setInput(q)}
                      className="px-4 py-2 rounded-full text-xs sm:text-sm transition-all glass-hover"
                      style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-fade-in`}>
              <div className={`max-w-[85%] sm:max-w-[78%] rounded-2xl px-4 sm:px-5 py-3.5 ${
                msg.agent_name === "debate" ? "border-l-2" : ""
              }`}
                style={{
                  background: msg.role === "user"
                    ? "hsla(239,84%,67%,0.12)"
                    : "hsla(240,28%,12%,0.65)",
                  border: msg.role === "user"
                    ? "1px solid hsla(239,84%,67%,0.2)"
                    : "1px solid var(--border)",
                  borderLeftColor: msg.agent_name === "debate" ? "hsl(270,70%,60%)" : undefined,
                  backdropFilter: msg.role === "assistant" ? "blur(12px)" : undefined,
                }}>
                {/* Agent Badge */}
                {msg.role === "assistant" && msg.agent_name && (
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm">{AGENT_ICONS[msg.agent_name] || "🤖"}</span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        background: `${AGENT_COLORS[msg.agent_name] || "hsl(220,10%,45%)"}18`,
                        color: AGENT_COLORS[msg.agent_name] || "var(--text-muted)",
                      }}>
                      {msg.agent_name}
                    </span>
                  </div>
                )}

                <MarkdownRenderer content={msg.content} />

                {/* Citations */}
                {msg.citations && msg.citations.length > 0 && (
                  <details className="mt-3">
                    <summary className="text-xs text-[var(--text-muted)] cursor-pointer hover:text-[var(--text-primary)] transition-colors">
                      📄 인용 문서 ({msg.citations.length}건)
                    </summary>
                    <div className="mt-2 space-y-1.5 text-xs">
                      {msg.citations.map((c) => (
                        <div key={c.number} className="flex gap-2 text-[var(--text-secondary)]">
                          <span className="font-mono" style={{ color: "var(--accent-light)" }}>[{c.number}]</span>
                          <span className="flex-1">{c.title}</span>
                          <span style={{ color: "var(--success)" }}>{(c.score * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          ))}

          {/* Streaming */}
          {loading && (
            <div className="flex justify-start animate-fade-in">
              <div className="max-w-[85%] sm:max-w-[78%] rounded-2xl px-4 sm:px-5 py-3.5 glass">
                {steps.length > 0 && (
                  <div className="mb-3 space-y-1.5">
                    {steps.map((s, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className="w-4 text-center">
                          {s.status === "completed" ? "✅" : s.status === "failed" ? "❌" : s.status === "executing" ? "🔄" : "⏳"}
                        </span>
                        <span style={{ color: AGENT_COLORS[s.agent] || "var(--text-muted)" }}>
                          {AGENT_ICONS[s.agent] || ""} {s.agent}
                        </span>
                        {s.error && <span className="text-[var(--error)]">— {s.error}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {streamingAgent && (
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm">{AGENT_ICONS[streamingAgent] || "🤖"}</span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        background: `${AGENT_COLORS[streamingAgent] || "#888"}18`,
                        color: AGENT_COLORS[streamingAgent] || "var(--text-muted)",
                      }}>
                      {streamingAgent}
                    </span>
                  </div>
                )}

                {streamingContent ? (
                  <div>
                    <MarkdownRenderer content={streamingContent} />
                    <span className="inline-block w-1.5 h-4 ml-0.5 animate-pulse rounded-sm"
                      style={{ background: "var(--accent)" }} />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-[var(--text-muted)]">
                    <span className="animate-pulse text-lg">🧠</span>
                    <span className="text-sm">생각 중...</span>
                  </div>
                )}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-3 sm:p-4 border-t border-[var(--border)]"
          style={{ background: "var(--bg-secondary)" }}>
          <div className="flex gap-2 sm:gap-3 max-w-4xl mx-auto items-end">
            {/* Debate Toggle */}
            <button onClick={() => setDebateMode(!debateMode)}
              className="shrink-0 px-2.5 py-2 rounded-lg text-sm transition-all"
              title={debateMode ? "Debate 모드 (3모델 토론)" : "일반 모드"}
              style={{
                background: debateMode ? "hsla(270,70%,60%,0.18)" : "transparent",
                color: debateMode ? "hsl(270,78%,68%)" : "var(--text-muted)",
                border: debateMode ? "1px solid hsla(270,70%,60%,0.3)" : "1px solid transparent",
              }}>
              🏛️
            </button>

            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={debateMode ? "토론 주제를 입력하세요..." : "연구에 대해 무엇이든 물어보세요..."}
              rows={1}
              className="flex-1 resize-none rounded-xl px-4 py-2.5 text-sm focus:outline-none transition-all"
              style={{
                background: debateMode ? "hsla(270,20%,18%,0.6)" : "var(--bg-tertiary)",
                border: debateMode ? "1px solid hsla(270,70%,60%,0.25)" : "1px solid var(--border)",
                color: "var(--text-primary)",
                maxHeight: "160px",
              }}
              disabled={loading}
            />

            <button onClick={handleSend}
              disabled={loading || !input.trim()}
              className="shrink-0 px-4 sm:px-6 py-2.5 rounded-xl text-white font-medium text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: loading ? "var(--text-muted)" : "var(--gradient-brand)",
              }}>
              {loading ? "..." : "전송"}
            </button>
          </div>

          {debateMode && (
            <div className="text-center mt-2 text-[10px]" style={{ color: "hsl(270,70%,55%)" }}>
              🏛️ Debate 모드 — 3개 LLM이 토론하여 답변합니다
            </div>
          )}
        </div>
      </main>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 animate-fade-in-scale">
          <div className="glass px-4 py-2.5 rounded-xl text-sm text-[var(--text-primary)] shadow-lg">
            {toast}
          </div>
        </div>
      )}
    </div>
  );
}
