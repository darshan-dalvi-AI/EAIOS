import { Activity, Bot, GitBranch, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { AGENTS, nextFeedEvent } from "../lib/mock";
import { useOS } from "../store";
import type { FeedEvent } from "../types";

export default function AgentsApp() {
  const { wsConnected, liveFeed } = useOS();
  const [agents, setAgents] = useState(AGENTS);
  const [mockFeed, setMockFeed] = useState<FeedEvent[]>(() => [nextFeedEvent(), nextFeedEvent(), nextFeedEvent()]);

  // Demo mode: simulated ticker. Live mode: real events arrive via WebSocket
  // into the store (agents flip active on agent.step events below).
  useEffect(() => {
    if (wsConnected) return;
    const timer = setInterval(() => {
      setMockFeed((f) => [nextFeedEvent(), ...f].slice(0, 30));
      setAgents((all) => {
        const i = Math.floor(Math.random() * all.length);
        return all.map((a, j) => (j === i ? { ...a, status: a.status === "active" ? "idle" : "active", runs: a.runs + 1 } : a));
      });
    }, 3500);
    return () => clearInterval(timer);
  }, [wsConnected]);

  // Live mode: reflect real agent.step events in the fleet cards
  useEffect(() => {
    if (!wsConnected || liveFeed.length === 0) return;
    const latest = liveFeed[0];
    if (latest.kind !== "run") return;
    setAgents((all) =>
      all.map((a) =>
        a.id === latest.agent
          ? {
              ...a,
              status: latest.text.startsWith("started") ? "active" : "idle",
              runs: latest.text.startsWith("done") ? a.runs + 1 : a.runs,
            }
          : a,
      ),
    );
  }, [wsConnected, liveFeed]);

  const feed = wsConnected ? liveFeed : mockFeed;
  const active = agents.filter((a) => a.status === "active").length;

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      <div className="app-pane">
        <div className="app-toolbar">
          <GitBranch size={15} style={{ color: "#c4b5fd" }} />
          <span style={{ fontWeight: 600, fontSize: 13 }}>Agent Fleet</span>
          <span className="pill good">{active} active</span>
          <span className="pill dim">{agents.length} registered</span>
          <span className="faint" style={{ marginLeft: "auto", fontSize: 11.5 }}>
            Planner → routes → specialist agents
          </span>
        </div>

        <div className="app-content">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 12 }}>
            {agents.map((agent) => (
              <div key={agent.id} className="card hover" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div className="app-icon md" style={{ "--hue": agent.hue } as React.CSSProperties}>
                    <Bot size={16} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{agent.name}</div>
                    <span className={`pill ${agent.status === "active" ? "good" : "dim"}`} style={{ marginTop: 2 }}>
                      {agent.status === "active" && <span className="dot pulse" style={{ width: 5, height: 5 }} />}
                      {agent.status}
                    </span>
                  </div>
                </div>
                <p className="muted" style={{ margin: 0, fontSize: 12, lineHeight: 1.5 }}>{agent.description}</p>
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                  {agent.capabilities.map((c) => <span key={c} className="pill dim">{c}</span>)}
                </div>
                <div style={{ display: "flex", gap: 14, fontSize: 11.5, color: "var(--text-faint)", marginTop: "auto" }}>
                  <span><Activity size={11} style={{ verticalAlign: -1.5 }} /> {agent.runs.toLocaleString()} runs</span>
                  <span><Zap size={11} style={{ verticalAlign: -1.5 }} /> {agent.avg_ms} ms avg</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <aside className="app-sidebar" style={{ width: 285, borderRight: "none", borderLeft: "1px solid var(--hairline)", padding: "14px 14px 8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span className="dot pulse" style={{ background: "var(--accent)" }} />
          <h3 className="h-display" style={{ fontSize: 13.5 }}>Live activity</h3>
        </div>
        <div style={{ overflowY: "auto" }}>
          {feed.length === 0 && (
            <p className="faint" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
              {wsConnected
                ? "Connected — events will stream here the moment an agent runs. Try asking something in AI Chat."
                : "Waiting for activity…"}
            </p>
          )}
          {feed.map((event) => (
            <div key={event.id} className="feed-item">
              <span className="feed-time">{event.time}</span>
              <span>
                <span className={`pill ${event.kind === "auth" ? "warn" : event.kind === "index" ? "info" : "dim"}`} style={{ marginRight: 6 }}>
                  {event.agent}
                </span>
                <span className="muted">{event.text}</span>
              </span>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
