/* Agent Studio — compose a custom AI agent with no code: a name, a system
   prompt, and a couple of tool toggles (knowledge-base RAG, web search).
   Saved agents run through the same runtime as the built-in fleet and show
   up in Chat's Route picker. */
import { Bot, Globe, Loader2, Play, Plus, Save, Trash2, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiStudioDelete, apiStudioList, apiStudioRun, apiStudioSave, type StudioAgent, type StudioDraft } from "../lib/api";

const BLANK: StudioDraft = {
  name: "", description: "", system_prompt: "You are a helpful enterprise assistant. ", tools: [], hue: 265, enabled: true,
};
const HUES = [265, 200, 150, 30, 340, 95, 220];

export default function StudioApp() {
  const [agents, setAgents] = useState<StudioAgent[]>([]);
  const [editing, setEditing] = useState<StudioAgent | null>(null);
  const [draft, setDraft] = useState<StudioDraft>(BLANK);
  const [saving, setSaving] = useState(false);
  const [testIn, setTestIn] = useState("");
  const [testOut, setTestOut] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => { apiStudioList().then(setAgents).catch(() => {}); }, []);

  function newAgent() { setEditing(null); setDraft(BLANK); setTestOut(null); }
  function edit(a: StudioAgent) {
    setEditing(a);
    setDraft({ name: a.name, description: a.description, system_prompt: a.system_prompt, tools: a.tools, hue: a.hue, enabled: a.enabled });
    setTestOut(null);
  }
  function toggleTool(t: string) {
    setDraft((d) => ({ ...d, tools: d.tools.includes(t) ? d.tools.filter((x) => x !== t) : [...d.tools, t] }));
  }
  async function save() {
    if (draft.name.trim().length < 2 || draft.system_prompt.trim().length < 10 || saving) return;
    setSaving(true);
    try {
      const saved = await apiStudioSave(draft, editing?.id);
      setAgents(await apiStudioList());
      setEditing(saved);
    } finally { setSaving(false); }
  }
  async function remove(a: StudioAgent) {
    await apiStudioDelete(a.id);
    setAgents((list) => list.filter((x) => x.id !== a.id));
    if (editing?.id === a.id) newAgent();
  }
  async function test() {
    if (!editing || !testIn.trim() || testing) return;
    setTesting(true); setTestOut(null);
    try { setTestOut((await apiStudioRun(editing.id, testIn.trim())).answer); } finally { setTesting(false); }
  }

  return (
    <div className="app-pane" style={{ flexDirection: "row" }}>
      {/* roster */}
      <aside className="app-sidebar" style={{ width: 230, padding: 12, gap: 8 }}>
        <button className="btn primary sm" style={{ justifyContent: "center" }} onClick={newAgent}><Plus size={13} /> New agent</button>
        {agents.length === 0 && <p className="faint" style={{ fontSize: 11.5, margin: "8px 0" }}>No custom agents yet. Create one — it appears in Chat's Route picker.</p>}
        {agents.map((a) => (
          <button key={a.id} className="card hover" onClick={() => edit(a)}
                  style={{ textAlign: "left", padding: "9px 11px", display: "flex", gap: 9, alignItems: "center", cursor: "pointer", borderColor: editing?.id === a.id ? "var(--accent)" : undefined }}>
            <span className="app-icon" style={{ width: 30, height: 30, borderRadius: 8, "--hue": a.hue } as React.CSSProperties}><Bot size={15} /></span>
            <span style={{ minWidth: 0 }}>
              <span style={{ display: "block", fontSize: 12.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.name}</span>
              <span className="faint" style={{ fontSize: 10 }}>{a.tools.join(" · ") || "no tools"} · {a.run_count} runs</span>
            </span>
          </button>
        ))}
      </aside>

      {/* editor */}
      <div className="app-content" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Wand2 size={15} style={{ color: "var(--accent)" }} />
          <span style={{ fontWeight: 600, fontSize: 13.5 }}>{editing ? `Editing “${editing.name}”` : "New agent"}</span>
          {editing && <span className="pill dim mono" style={{ marginLeft: 4 }}>{editing.slug}</span>}
          {editing && <button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => remove(editing)}><Trash2 size={12} /> Delete</button>}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div className="field" style={{ flex: 1, minWidth: 180 }}>
            <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Agent name (e.g. HR Helper)" aria-label="Agent name" />
          </div>
          <div className="field" style={{ flex: 2, minWidth: 200 }}>
            <input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} placeholder="Short description" aria-label="Agent description" />
          </div>
        </div>

        <label className="faint" style={{ fontSize: 11 }}>System prompt — this defines the agent’s personality & task</label>
        <textarea className="input" rows={6} style={{ resize: "vertical", fontFamily: "var(--font-ui, inherit)", fontSize: 12.5 }}
                  value={draft.system_prompt} onChange={(e) => setDraft({ ...draft, system_prompt: e.target.value })} aria-label="System prompt" />

        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <span className="faint" style={{ fontSize: 11 }}>Tools:</span>
          <button className={`btn sm ${draft.tools.includes("rag") ? "primary" : ""}`} onClick={() => toggleTool("rag")}><Bot size={12} /> Knowledge base (RAG)</button>
          <button className={`btn sm ${draft.tools.includes("web") ? "primary" : ""}`} onClick={() => toggleTool("web")}><Globe size={12} /> Web search</button>
          <span className="faint" style={{ fontSize: 11, marginLeft: 12 }}>Color:</span>
          {HUES.map((h) => (
            <button key={h} onClick={() => setDraft({ ...draft, hue: h })} aria-label={`Color ${h}`}
                    style={{ width: 20, height: 20, borderRadius: 6, cursor: "pointer", border: draft.hue === h ? "2px solid var(--text)" : "1px solid var(--hairline)", background: `hsl(${h}, 70%, 50%)` }} />
          ))}
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn primary" onClick={save} disabled={saving || draft.name.trim().length < 2 || draft.system_prompt.trim().length < 10}>
            {saving ? <Loader2 size={13} className="spin" /> : <Save size={13} />} {editing ? "Save changes" : "Create agent"}
          </button>
        </div>

        {/* test panel */}
        {editing && (
          <div className="card" style={{ marginTop: 4 }}>
            <div className="palette-section" style={{ padding: "0 0 8px" }}>Test this agent</div>
            <div style={{ display: "flex", gap: 8 }}>
              <div className="field" style={{ flex: 1 }}>
                <input value={testIn} onChange={(e) => setTestIn(e.target.value)} placeholder="Ask your agent something…"
                       onKeyDown={(e) => e.key === "Enter" && test()} aria-label="Test input" />
              </div>
              <button className="btn sm" onClick={test} disabled={testing || !testIn.trim()}>
                {testing ? <Loader2 size={12} className="spin" /> : <Play size={12} />} Run
              </button>
            </div>
            {testOut && <div className="bubble" style={{ marginTop: 10, whiteSpace: "pre-wrap", fontSize: 12.5 }}>{testOut}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
