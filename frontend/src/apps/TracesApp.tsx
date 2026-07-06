/* Traces — observability for every chat request and workflow run.
   Langfuse-style span waterfall served from the backend's in-process trace
   buffer (optionally mirrored to OTel/Langfuse when configured). */
import { Activity, ChevronRight, Clock, RefreshCw, User } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiTrace, apiTraces } from "../lib/api";
import type { TraceInfo, TraceSpan } from "../types";

const KIND_HUE: Record<TraceSpan["kind"], number> = {
  agent: 265, llm: 200, retrieval: 155, graph: 175, node: 38, step: 220,
};

export default function TracesApp() {
  const [traces, setTraces] = useState<TraceInfo[]>([]);
  const [detail, setDetail] = useState<TraceInfo | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<TraceSpan | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await apiTraces();
      setTraces(list);
      if (list.length > 0) {
        const first = await apiTrace(list[0].id);
        setDetail(first);
      } else {
        setDetail(null);
      }
    } catch {
      setTraces([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openTrace = async (t: TraceInfo) => {
    setSelectedSpan(null);
    try {
      setDetail(await apiTrace(t.id));
    } catch {
      setDetail({ ...t, spans: [] });
    }
  };

  const total = Math.max(1, detail?.duration_ms ?? 1);

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      {/* ── left: trace list ── */}
      <aside className="app-sidebar" style={{ width: 268, padding: "12px 10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <Activity size={14} style={{ color: "#f0abfc" }} />
          <h3 className="h-display" style={{ fontSize: 13.5, margin: 0 }}>Traces</h3>
          <span className="pill dim">{traces.length}</span>
          <button className="btn sm" style={{ marginLeft: "auto" }} onClick={load} title="Refresh">
            <RefreshCw size={12} />
          </button>
        </div>
        <div style={{ overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
          {loading && <p className="faint" style={{ fontSize: 11.5 }}>Loading…</p>}
          {!loading && traces.length === 0 && (
            <p className="faint" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
              No traces yet — every AI Chat request and workflow run is traced automatically. Ask something and refresh.
            </p>
          )}
          {traces.map((t) => (
            <button key={t.id} className="card hover" onClick={() => openTrace(t)}
              style={{ padding: "8px 10px", textAlign: "left", borderColor: detail?.id === t.id ? "var(--accent)" : undefined }}>
              <div style={{ fontSize: 12, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.name}
              </div>
              <div style={{ display: "flex", gap: 5, marginTop: 6, alignItems: "center", flexWrap: "wrap" }}>
                <span className={`pill ${t.status === "ok" ? "good" : "warn"}`}>{t.status}</span>
                <span className="pill dim">{t.kind}</span>
                <span className="faint" style={{ fontSize: 10.5 }}>
                  {t.duration_ms} ms · {t.span_count ?? t.spans?.length ?? 0} spans
                </span>
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* ── right: waterfall ── */}
      <div className="app-pane">
        {detail ? (
          <>
            <div className="app-toolbar" style={{ flexWrap: "wrap" }}>
              <span style={{ fontWeight: 600, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "55%" }}>
                {detail.name}
              </span>
              <span className="pill dim"><User size={10} style={{ verticalAlign: -1 }} /> {detail.user}</span>
              <span className="pill dim"><Clock size={10} style={{ verticalAlign: -1 }} /> {detail.duration_ms} ms</span>
              <span className={`pill ${detail.status === "ok" ? "good" : "warn"}`}>{detail.status}</span>
              <span className="faint" style={{ marginLeft: "auto", fontSize: 11 }}>trace {detail.id}</span>
            </div>

            <div className="app-content">
              {/* time ruler */}
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-faint)", padding: "0 2px 6px 176px" }}>
                {[0, 0.25, 0.5, 0.75, 1].map((f) => <span key={f}>{Math.round(total * f)} ms</span>)}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {(detail.spans ?? []).map((s, i) => {
                  const hue = KIND_HUE[s.kind] ?? 220;
                  const left = (s.offset_ms / total) * 100;
                  const width = Math.max(1.2, (s.duration_ms / total) * 100);
                  return (
                    <button key={i} onClick={() => setSelectedSpan(s)}
                      style={{ display: "flex", alignItems: "center", gap: 8, background: selectedSpan === s ? "rgba(148,163,184,0.08)" : "transparent", borderRadius: 8, padding: "3px 4px", textAlign: "left" }}>
                      <span style={{ width: 164, flexShrink: 0, fontSize: 11.5, display: "flex", alignItems: "center", gap: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        <span className="dot" style={{ background: `hsl(${hue}, 85%, 60%)`, width: 7, height: 7, flexShrink: 0 }} />
                        {s.name}
                      </span>
                      <span style={{ position: "relative", flex: 1, height: 16, background: "rgba(148,163,184,0.06)", borderRadius: 5, overflow: "hidden" }}>
                        <span style={{
                          position: "absolute", left: `${left}%`, width: `${width}%`, top: 2, bottom: 2, borderRadius: 4,
                          background: `linear-gradient(90deg, hsla(${hue}, 85%, 55%, 0.85), hsla(${hue}, 85%, 65%, 0.55))`,
                          boxShadow: s.status === "error" ? "0 0 0 1.5px hsl(0, 85%, 60%)" : undefined,
                        }} />
                      </span>
                      <span className="faint" style={{ width: 62, flexShrink: 0, fontSize: 10.5, textAlign: "right" }}>
                        {s.duration_ms} ms
                      </span>
                    </button>
                  );
                })}
                {(detail.spans ?? []).length === 0 && (
                  <p className="faint" style={{ fontSize: 12 }}>This trace recorded no spans.</p>
                )}
              </div>

              {/* span detail */}
              {selectedSpan && (
                <div className="card" style={{ marginTop: 14, padding: "10px 12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <ChevronRight size={13} style={{ color: `hsl(${KIND_HUE[selectedSpan.kind] ?? 220}, 85%, 60%)` }} />
                    <b style={{ fontSize: 12.5 }}>{selectedSpan.name}</b>
                    <span className="pill dim">{selectedSpan.kind}</span>
                    <span className="faint" style={{ fontSize: 11 }}>
                      +{selectedSpan.offset_ms} ms → {selectedSpan.offset_ms + selectedSpan.duration_ms} ms
                    </span>
                  </div>
                  {Object.entries(selectedSpan.attrs ?? {}).map(([key, value]) => (
                    <div key={key} style={{ display: "flex", gap: 8, fontSize: 11.5, padding: "2px 0" }}>
                      <span className="faint" style={{ width: 100, flexShrink: 0 }}>{key}</span>
                      <span className="muted" style={{ wordBreak: "break-word" }}>{String(value)}</span>
                    </div>
                  ))}
                </div>
              )}

              <p className="faint" style={{ fontSize: 10.5, lineHeight: 1.6, marginTop: 14 }}>
                Spans: <span style={{ color: "hsl(265,85%,70%)" }}>agent</span> ·{" "}
                <span style={{ color: "hsl(200,85%,70%)" }}>llm</span> ·{" "}
                <span style={{ color: "hsl(155,85%,70%)" }}>retrieval</span> ·{" "}
                <span style={{ color: "hsl(175,85%,70%)" }}>graph</span>. Set{" "}
                <code>OTEL_EXPORTER_OTLP_ENDPOINT</code> or Langfuse keys to mirror these to external dashboards.
              </p>
            </div>
          </>
        ) : (
          <div className="empty">
            <Activity size={26} style={{ opacity: 0.5 }} />
            <div>Select a trace — every chat request and workflow run records a span waterfall.</div>
          </div>
        )}
      </div>
    </div>
  );
}
