"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Session } from "@/lib/types";

const NAV_ITEMS = [
  { href: "/", icon: "💬", label: "채팅" },
  { href: "/research", icon: "🧭", label: "연구 리뷰" },
  { href: "/dashboard", icon: "📊", label: "대시보드" },
  { href: "/knowledge", icon: "🕸️", label: "지식그래프" },
];

interface SidebarProps {
  serverOnline: boolean;
  sessions?: Session[];
  activeSessionId?: string;
  onSelectSession?: (id: string) => void;
  onNewConversation?: () => void;
  onDeleteSession?: (id: string) => void;
}

function formatTimeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);
  if (diffMin < 1) return "방금";
  if (diffMin < 60) return `${diffMin}분 전`;
  if (diffHr < 24) return `${diffHr}시간 전`;
  if (diffDay < 7) return `${diffDay}일 전`;
  return date.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

export default function Sidebar({
  serverOnline,
  sessions = [],
  activeSessionId,
  onSelectSession,
  onNewConversation,
  onDeleteSession,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-[240px] flex-col border-r border-[var(--border)] shrink-0"
        style={{ background: "linear-gradient(180deg, hsla(240,30%,8%,0.95), hsla(240,33%,6%,0.98))" }}
      >
        {/* Logo */}
        <div className="p-5 border-b border-[var(--border)]">
          <h1 className="text-base font-bold bg-clip-text text-transparent"
            style={{ backgroundImage: "var(--gradient-brand)" }}
          >
            🧠 CEML Lab
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <span className={`status-dot ${serverOnline ? "status-online" : "status-offline"}`} />
            <span className="text-[11px] text-[var(--text-muted)]">
              {serverOnline ? "서버 연결됨" : "오프라인"}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="p-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`nav-item ${pathname === item.href ? "active" : ""}`}
            >
              <span className="text-lg">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        {/* Conversation History */}
        {pathname === "/" && (
          <div className="flex-1 flex flex-col min-h-0 border-t border-[var(--border)]">
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                대화 기록
              </span>
              {onNewConversation && (
                <button
                  onClick={onNewConversation}
                  className="text-[11px] px-2 py-0.5 rounded-md transition-all hover:bg-[var(--card-hover)]"
                  style={{ color: "var(--accent-light)" }}
                  title="새 대화"
                >
                  ✨ 새 대화
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5"
              style={{ scrollbarWidth: "thin", scrollbarColor: "hsl(240,10%,25%) transparent" }}
            >
              {sessions.length === 0 ? (
                <div className="text-[11px] text-[var(--text-muted)] px-2 py-4 text-center">
                  대화 기록이 없습니다
                </div>
              ) : (
                sessions.map((session) => (
                  <div
                    key={session.conversation_id}
                    className="group flex items-center rounded-lg px-2.5 py-2 cursor-pointer transition-all"
                    style={{
                      background: activeSessionId === session.conversation_id
                        ? "hsla(var(--accent-hue, 240), 60%, 50%, 0.15)"
                        : "transparent",
                      borderLeft: activeSessionId === session.conversation_id
                        ? "2px solid var(--accent-light)"
                        : "2px solid transparent",
                    }}
                    onClick={() => onSelectSession?.(session.conversation_id)}
                    onMouseEnter={(e) => {
                      if (activeSessionId !== session.conversation_id) {
                        (e.currentTarget as HTMLDivElement).style.background = "hsla(240,10%,20%,0.5)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (activeSessionId !== session.conversation_id) {
                        (e.currentTarget as HTMLDivElement).style.background = "transparent";
                      }
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] text-[var(--text-primary)] truncate leading-tight">
                        {session.title}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <span className="text-[10px] text-[var(--text-muted)]">
                          {formatTimeAgo(session.last_message_at)}
                        </span>
                        <span className="text-[9px] text-[var(--text-muted)]">·</span>
                        <span className="text-[10px] text-[var(--text-muted)]">
                          {session.message_count}개
                        </span>
                      </div>
                    </div>
                    {onDeleteSession && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(session.conversation_id);
                        }}
                        className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-[12px] p-1 rounded transition-opacity"
                        title="삭제"
                      >
                        🗑️
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="p-4 border-t border-[var(--border)]">
          <div className="text-[10px] text-[var(--text-muted)]">
            Lab Orchestrator v0.3.0
          </div>
        </div>
      </aside>

      {/* Mobile Bottom Navigation */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around py-2 border-t border-[var(--border)]"
        style={{ background: "hsla(240,30%,8%,0.95)", backdropFilter: "blur(16px)" }}>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="flex flex-col items-center gap-0.5 py-1 px-4 rounded-lg transition-all"
            style={{
              color: pathname === item.href ? "var(--accent-light)" : "var(--text-muted)",
            }}
          >
            <span className="text-xl">{item.icon}</span>
            <span className="text-[10px] font-medium">{item.label}</span>
          </Link>
        ))}
      </nav>
    </>
  );
}
