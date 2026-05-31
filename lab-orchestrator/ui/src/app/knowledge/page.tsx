"use client";

import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import Sidebar from "@/components/Sidebar";
import { checkHealth, fetchGraphData, GraphNode, GraphEdge, searchMemory } from "@/lib/api";

// react-force-graph-2d is client-only, so dynamic import with ssr:false
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const GROUP_COLORS: Record<string, string> = {
  default: "#818cf8",
  material: "#6366f1",
  method: "#10b981",
  person: "#f59e0b",
  concept: "#ec4899",
  decision: "#06b6d4",
};

function getNodeColor(group: string): string {
  return GROUP_COLORS[group] || GROUP_COLORS.default;
}

export default function KnowledgePage() {
  const [online, setOnline] = useState(false);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeFacts, setNodeFacts] = useState<{ fact: string; created_at: string | null }[]>([]);
  const [filterText, setFilterText] = useState("");

  useEffect(() => {
    const load = async () => {
      const isOnline = await checkHealth();
      setOnline(isOnline);
      if (!isOnline) { setLoading(false); return; }
      try {
        const data = await fetchGraphData(150);
        setNodes(data.nodes);
        setEdges(data.edges);
      } catch (e) { console.error(e); }
      setLoading(false);
    };
    load();
  }, []);

  const handleNodeClick = useCallback(async (node: Record<string, unknown>) => {
    const nodeId = String(node.id || "");
    const found = nodes.find((n) => n.id === nodeId);
    if (!found) return;
    setSelectedNode(found);
    try {
      const results = await searchMemory(found.id, 10);
      setNodeFacts(results.results.map((r) => ({ fact: r.fact, created_at: r.created_at })));
    } catch {
      setNodeFacts([]);
    }
  }, [nodes]);

  const filteredNodes = filterText
    ? nodes.filter((n) => n.id.toLowerCase().includes(filterText.toLowerCase()))
    : nodes;

  const filteredEdges = filterText
    ? edges.filter((e) => {
        const nodeIds = new Set(filteredNodes.map((n) => n.id));
        return nodeIds.has(e.source) && nodeIds.has(e.target);
      })
    : edges;

  const graphData = {
    nodes: filteredNodes.map((n) => ({
      id: n.id,
      name: n.id,
      val: Math.max(2, n.degree * 2),
      color: getNodeColor(n.group),
      summary: n.summary,
      degree: n.degree,
      group: n.group,
    })),
    links: filteredEdges.map((e) => ({
      source: e.source,
      target: e.target,
      label: e.relation,
      fact: e.fact,
    })),
  };

  return (
    <div className="flex h-screen">
      <Sidebar serverOnline={online} />

      <main className="flex-1 flex overflow-hidden">
        {/* Graph Area */}
        <div className="flex-1 relative">
          {/* Header */}
          <div className="absolute top-4 left-4 right-4 z-10 flex items-center gap-3">
            <div className="glass-light flex-1 flex items-center px-4 py-2.5">
              <span className="text-[var(--text-muted)] mr-2">🔍</span>
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="노드 검색..."
                className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none"
              />
              {filterText && (
                <button
                  onClick={() => setFilterText("")}
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                >
                  ✕
                </button>
              )}
            </div>
            <div className="glass-light px-3 py-2.5 text-xs text-[var(--text-secondary)]">
              {filteredNodes.length} 노드 · {filteredEdges.length} 엣지
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="text-5xl mb-4 animate-float">🕸️</div>
                <div className="text-sm text-[var(--text-muted)]">지식그래프 로딩 중...</div>
              </div>
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <div className="text-5xl mb-4">🕸️</div>
                <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
                  지식그래프가 비어있습니다
                </h2>
                <p className="text-sm text-[var(--text-muted)]">
                  대화를 진행하면 엔티티와 관계가 자동으로 추출되어 지식그래프에 저장됩니다.
                </p>
              </div>
            </div>
          ) : (
            <ForceGraph2D
              graphData={graphData}
              nodeLabel={(node: Record<string, unknown>) => `${node.name}\n${node.summary || ""}`}
              nodeColor={(node: Record<string, unknown>) => (node.color as string) || "#818cf8"}
              nodeRelSize={4}
              linkColor={() => "hsla(240, 15%, 35%, 0.5)"}
              linkWidth={1}
              linkDirectionalParticles={1}
              linkDirectionalParticleWidth={2}
              linkDirectionalParticleColor={() => "hsla(239, 84%, 67%, 0.6)"}
              linkLabel={(link: Record<string, unknown>) => (link.label as string) || ""}
              onNodeClick={handleNodeClick}
              backgroundColor="hsl(240, 33%, 6%)"
              width={typeof window !== "undefined" ? window.innerWidth - 220 - (selectedNode ? 360 : 0) : 800}
              height={typeof window !== "undefined" ? window.innerHeight : 600}
              nodeCanvasObject={(node: Record<string, unknown>, ctx: CanvasRenderingContext2D, globalScale: number) => {
                const label = node.name as string;
                const fontSize = Math.max(10 / globalScale, 3);
                const nodeVal = (node.val as number) || 4;
                const radius = Math.sqrt(nodeVal) * 2;

                // Node circle
                ctx.beginPath();
                ctx.arc(node.x as number, node.y as number, radius, 0, 2 * Math.PI);
                ctx.fillStyle = (node.color as string) || "#818cf8";
                ctx.fill();

                // Glow
                ctx.shadowColor = (node.color as string) || "#818cf8";
                ctx.shadowBlur = 8;
                ctx.fill();
                ctx.shadowBlur = 0;

                // Label
                if (globalScale > 0.8) {
                  ctx.font = `${fontSize}px Inter, sans-serif`;
                  ctx.textAlign = "center";
                  ctx.textBaseline = "top";
                  ctx.fillStyle = "hsla(240, 30%, 90%, 0.9)";
                  ctx.fillText(label, node.x as number, (node.y as number) + radius + 2);
                }
              }}
            />
          )}
        </div>

        {/* Side Panel */}
        {selectedNode && (
          <div className="w-[360px] border-l border-[var(--border)] overflow-y-auto animate-slide-in"
            style={{ background: "var(--bg-secondary)" }}
          >
            <div className="p-5">
              {/* Node Header */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-[var(--text-primary)]">
                  {selectedNode.id}
                </h3>
                <button
                  onClick={() => setSelectedNode(null)}
                  className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-lg"
                >
                  ✕
                </button>
              </div>

              {/* Node Info */}
              <div className="glass p-3 mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                    style={{
                      background: `${getNodeColor(selectedNode.group)}25`,
                      color: getNodeColor(selectedNode.group),
                    }}
                  >
                    {selectedNode.group}
                  </span>
                  <span className="text-xs text-[var(--text-muted)]">
                    {selectedNode.degree} 연결
                  </span>
                </div>
                {selectedNode.summary && (
                  <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
                    {selectedNode.summary}
                  </p>
                )}
              </div>

              {/* Related Facts */}
              <h4 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
                관련 기억 ({nodeFacts.length})
              </h4>
              <div className="space-y-2">
                {nodeFacts.length === 0 ? (
                  <div className="text-xs text-[var(--text-muted)] text-center py-4">
                    관련 기억이 없습니다
                  </div>
                ) : (
                  nodeFacts.map((f, i) => (
                    <div key={i} className="glass-light p-3">
                      <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                        {f.fact}
                      </p>
                      {f.created_at && (
                        <div className="text-[10px] text-[var(--text-muted)] mt-1.5">
                          {new Date(f.created_at).toLocaleDateString("ko-KR")}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
