/* Graph — knowledge-graph explorer.
   Custom force-directed SVG layout (no chart library): repulsion + edge
   springs + center gravity, drag nodes, wheel zoom, click for entity detail.
   Entities and co-occurrence edges are extracted automatically at ingest. */
import { RefreshCw, Search, Share2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiGraph } from "../lib/api";
import type { GraphEdge, GraphNode } from "../types";

const TYPE_HUE: Record<string, number> = {
  person: 330, org: 45, money: 130, date: 210, acronym: 265, concept: 175, term: 200,
};

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export default function GraphApp() {
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [, forceTick] = useState(0);

  const simRef = useRef<SimNode[]>([]);
  const dragRef = useRef<{ node: SimNode; dx: number; dy: number } | null>(null);
  const viewRef = useRef({ x: 0, y: 0, k: 1 });
  const svgRef = useRef<SVGSVGElement>(null);
  const runningRef = useRef(true);

  const load = useCallback(async (q = "") => {
    setLoading(true);
    setSelected(null);
    try {
      const data = await apiGraph(q);
      const W = 900, H = 560;
      const sim: SimNode[] = data.nodes.map((n, i) => {
        const angle = (i / Math.max(1, data.nodes.length)) * Math.PI * 2;
        const r = 140 + (i % 5) * 42;
        return { ...n, x: W / 2 + Math.cos(angle) * r, y: H / 2 + Math.sin(angle) * r, vx: 0, vy: 0 };
      });
      simRef.current = sim;
      setNodes(sim);
      setEdges(data.edges);
    } catch {
      simRef.current = [];
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // ── physics loop ──
  useEffect(() => {
    runningRef.current = true;
    let raf = 0;
    let cooling = 1;
    const byId = () => new Map(simRef.current.map((n) => [n.id, n]));

    const step = () => {
      const sim = simRef.current;
      const map = byId();
      const W = 900, H = 560;
      if (sim.length > 0 && cooling > 0.02) {
        // pairwise repulsion
        for (let i = 0; i < sim.length; i++) {
          for (let j = i + 1; j < sim.length; j++) {
            const a = sim[i], b = sim[j];
            let dx = a.x - b.x, dy = a.y - b.y;
            let d2 = dx * dx + dy * dy;
            if (d2 < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 1; }
            const f = Math.min(1600 / d2, 8) * cooling;
            const d = Math.sqrt(d2);
            a.vx += (dx / d) * f; a.vy += (dy / d) * f;
            b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
          }
        }
        // edge springs
        for (const e of edges) {
          const a = map.get(e.source), b = map.get(e.target);
          if (!a || !b) continue;
          const dx = b.x - a.x, dy = b.y - a.y;
          const d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
          const target = 120 - Math.min(40, e.weight * 4);
          const f = ((d - target) / d) * 0.02 * cooling;
          a.vx += dx * f; a.vy += dy * f;
          b.vx -= dx * f; b.vy -= dy * f;
        }
        // gravity + integrate
        for (const n of sim) {
          n.vx += (W / 2 - n.x) * 0.0015 * cooling;
          n.vy += (H / 2 - n.y) * 0.0015 * cooling;
          if (dragRef.current?.node.id !== n.id) {
            n.x += n.vx; n.y += n.vy;
          }
          n.vx *= 0.82; n.vy *= 0.82;
        }
        cooling *= 0.995;
        forceTick((t) => t + 1);
      }
      if (runningRef.current) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    const reheat = () => { cooling = Math.max(cooling, 0.5); };
    window.addEventListener("pointermove", reheatIfDragging);
    function reheatIfDragging() { if (dragRef.current) reheat(); }
    return () => {
      runningRef.current = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", reheatIfDragging);
    };
  }, [edges, nodes.length]);

  // ── interactions ──
  const toWorld = (clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const { x, y, k } = viewRef.current;
    return {
      x: ((clientX - rect.left) / rect.width) * 900 / k - x,
      y: ((clientY - rect.top) / rect.height) * 560 / k - y,
    };
  };

  const onPointerDown = (e: React.PointerEvent, node: SimNode) => {
    e.stopPropagation();
    const p = toWorld(e.clientX, e.clientY);
    dragRef.current = { node, dx: node.x - p.x, dy: node.y - p.y };
    (e.target as Element).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const p = toWorld(e.clientX, e.clientY);
    drag.node.x = p.x + drag.dx;
    drag.node.y = p.y + drag.dy;
    forceTick((t) => t + 1);
  };
  const onPointerUp = () => { dragRef.current = null; };
  const onWheel = (e: React.WheelEvent) => {
    const v = viewRef.current;
    v.k = Math.min(2.6, Math.max(0.45, v.k * (e.deltaY > 0 ? 0.92 : 1.08)));
    forceTick((t) => t + 1);
  };

  const maxMentions = useMemo(() => Math.max(1, ...nodes.map((n) => n.mentions)), [nodes]);
  const nodeR = (n: GraphNode) => 7 + Math.sqrt(n.mentions / maxMentions) * 16;
  const neighborIds = useMemo(() => {
    if (!selected) return new Set<string>();
    const s = new Set<string>();
    edges.forEach((e) => {
      if (e.source === selected.id) s.add(e.target);
      if (e.target === selected.id) s.add(e.source);
    });
    return s;
  }, [selected, edges]);

  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const { x: vx, y: vy, k } = viewRef.current;

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      <div className="app-pane">
        <div className="app-toolbar">
          <Share2 size={15} style={{ color: "#5eead4" }} />
          <span style={{ fontWeight: 600, fontSize: 13 }}>Knowledge Graph</span>
          <span className="pill dim">{nodes.length} entities</span>
          <span className="pill dim">{edges.length} links</span>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
            <div style={{ position: "relative" }}>
              <Search size={12} style={{ position: "absolute", left: 8, top: 8, color: "var(--text-faint)" }} />
              <input
                className="input sm"
                style={{ paddingLeft: 26, width: 180 }}
                placeholder="Filter entities…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && load(query)}
              />
            </div>
            <button className="btn sm" onClick={() => load(query)} title="Reload graph">
              <RefreshCw size={12} />
            </button>
          </div>
        </div>

        <div className="app-content" style={{ padding: 0, position: "relative", overflow: "hidden" }}>
          {loading && <div className="empty" style={{ position: "absolute", inset: 0 }}>Mapping the constellation…</div>}
          {!loading && nodes.length === 0 && (
            <div className="empty" style={{ position: "absolute", inset: 0 }}>
              No entities yet — index a few documents in the Knowledge app and the graph will grow on its own.
            </div>
          )}
          <svg
            ref={svgRef}
            viewBox="0 0 900 560"
            style={{ width: "100%", height: "100%", cursor: dragRef.current ? "grabbing" : "default", touchAction: "none" }}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onWheel={onWheel}
            onClick={() => setSelected(null)}
          >
            <defs>
              <radialGradient id="kg-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="rgba(34,211,238,0.14)" />
                <stop offset="100%" stopColor="rgba(34,211,238,0)" />
              </radialGradient>
            </defs>
            <rect x="0" y="0" width="900" height="560" fill="url(#kg-glow)" pointerEvents="none" />
            <g transform={`scale(${k}) translate(${vx} ${vy})`}>
              {edges.map((e, i) => {
                const a = nodeMap.get(e.source), b = nodeMap.get(e.target);
                if (!a || !b) return null;
                const hot = selected && (e.source === selected.id || e.target === selected.id);
                return (
                  <line
                    key={i}
                    x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={hot ? "hsla(175, 90%, 62%, 0.75)" : "hsla(220, 60%, 70%, 0.16)"}
                    strokeWidth={hot ? 1.6 : Math.min(2.4, 0.5 + e.weight * 0.22)}
                  />
                );
              })}
              {nodes.map((n) => {
                const hue = TYPE_HUE[n.type] ?? 200;
                const r = nodeR(n);
                const dim = selected && selected.id !== n.id && !neighborIds.has(n.id);
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.x} ${n.y})`}
                    opacity={dim ? 0.25 : 1}
                    style={{ cursor: "grab", transition: "opacity .25s" }}
                    onPointerDown={(e) => onPointerDown(e, n)}
                    onClick={(e) => { e.stopPropagation(); setSelected(n); }}
                  >
                    <circle r={r + 5} fill={`hsla(${hue}, 90%, 60%, 0.12)`} />
                    <circle
                      r={r}
                      fill={`hsla(${hue}, 75%, 22%, 0.9)`}
                      stroke={`hsla(${hue}, 90%, ${selected?.id === n.id ? 75 : 58}%, ${selected?.id === n.id ? 1 : 0.8})`}
                      strokeWidth={selected?.id === n.id ? 2 : 1.2}
                    />
                    <text
                      y={r + 12}
                      textAnchor="middle"
                      style={{ fontSize: 10, fill: "var(--text-dim, #94a3b8)", pointerEvents: "none", userSelect: "none" }}
                    >
                      {n.name.length > 18 ? `${n.name.slice(0, 17)}…` : n.name}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>

          <div style={{ position: "absolute", left: 10, bottom: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
            {Object.entries(TYPE_HUE).map(([t, hue]) => (
              <span key={t} className="pill dim" style={{ gap: 5 }}>
                <span className="dot" style={{ background: `hsl(${hue}, 85%, 60%)`, width: 6, height: 6 }} />
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>

      {selected && (
        <aside className="app-sidebar" style={{ width: 270, borderRight: "none", borderLeft: "1px solid var(--hairline)", padding: 14 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <div>
              <h3 className="h-display" style={{ fontSize: 15, margin: 0 }}>{selected.name}</h3>
              <span className="pill info" style={{ marginTop: 6 }}>{selected.type}</span>
              <span className="pill dim" style={{ marginTop: 6, marginLeft: 6 }}>{selected.mentions} mentions</span>
            </div>
            <button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => setSelected(null)} aria-label="Close">
              <X size={12} />
            </button>
          </div>
          <h4 className="faint" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 1, margin: "16px 0 6px" }}>
            Connected to
          </h4>
          <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
            {edges
              .filter((e) => e.source === selected.id || e.target === selected.id)
              .sort((a, b) => b.weight - a.weight)
              .map((e, i) => {
                const other = nodeMap.get(e.source === selected.id ? e.target : e.source);
                if (!other) return null;
                return (
                  <button
                    key={i}
                    className="card hover"
                    style={{ padding: "7px 10px", textAlign: "left", display: "flex", alignItems: "center", gap: 8 }}
                    onClick={() => setSelected(other)}
                  >
                    <span className="dot" style={{ background: `hsl(${TYPE_HUE[other.type] ?? 200}, 85%, 60%)` }} />
                    <span style={{ fontSize: 12.5, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {other.name}
                    </span>
                    <span className="faint" style={{ fontSize: 10.5 }}>×{e.weight}</span>
                  </button>
                );
              })}
          </div>
          <p className="faint" style={{ fontSize: 11, lineHeight: 1.55, marginTop: 10 }}>
            Ask in AI Chat: “How are {selected.name} and … related?” — the Document Agent answers with graph paths + cited passages.
          </p>
        </aside>
      )}
    </div>
  );
}
