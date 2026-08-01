/* Code — collaborative editing.
 *
 * Several people can hold the same file open and type at once. That works
 * because the text is a CRDT (Yjs): each keystroke becomes a small binary
 * update that can arrive in any order and still converge to identical text
 * everywhere. The server never merges anything — it relays those updates and
 * stores the result (see backend/app/core/collab.py).
 *
 * Monaco is bundled, not loaded from a CDN: the app's Content-Security-Policy
 * allows scripts from 'self' only, so a CDN loader would be blocked.
 */
import {
  ChevronRight, Code2, FilePlus, FileText, History, Loader2, Plus, Save, Trash2, Users,
} from "lucide-react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker";
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import tsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";
import { useCallback, useEffect, useRef, useState } from "react";
import { MonacoBinding } from "y-monaco";
import * as Y from "yjs";
import {
  apiCreateFile, apiCreateProject, apiDeleteFile, apiDeleteProject,
  apiFileVersions, apiProjectFiles, apiProjects, apiReadFile, apiRestoreVersion, apiSaveFile,
} from "../lib/api";
import { useOS } from "../store";
import type { CodeFile, CodeProject, CollabPeer, FileVersionInfo } from "../types";

// Monaco resolves its language services through web workers. Vite bundles each
// as a same-origin chunk, which keeps this working under the app's CSP.
(self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
  getWorker(_: unknown, label: string) {
    if (label === "json") return new jsonWorker();
    if (label === "css" || label === "scss") return new cssWorker();
    if (label === "html") return new htmlWorker();
    if (label === "typescript" || label === "javascript") return new tsWorker();
    return new editorWorker();
  },
};

monaco.editor.defineTheme("eaios-dark", {
  base: "vs-dark", inherit: true, rules: [],
  colors: { "editor.background": "#0d1524", "editorGutter.background": "#0d1524" },
});

export default function CodeApp() {
  const { token, live, user } = useOS();
  const [projects, setProjects] = useState<CodeProject[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [files, setFiles] = useState<CodeFile[]>([]);
  const [fileId, setFileId] = useState<string | null>(null);
  const [peers, setPeers] = useState<CollabPeer[]>([]);
  const [versions, setVersions] = useState<FileVersionInfo[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");

  const hostRef = useRef<HTMLDivElement>(null);
  const edRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const teardown = useRef<(() => void) | null>(null);

  const activeFile = files.find((f) => f.id === fileId) || null;

  /* ── data ─────────────────────────────────────────────────────────── */
  const loadProjects = useCallback(async () => {
    try {
      const p = await apiProjects();
      setProjects(p);
      setProjectId((cur) => cur ?? (p[0]?.id ?? null));
    } catch (e) { setErr((e as Error).message); }
  }, []);

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  useEffect(() => {
    if (!projectId) { setFiles([]); return; }
    apiProjectFiles(projectId)
      .then((f) => { setFiles(f); setFileId((cur) => (f.some((x) => x.id === cur) ? cur : f[0]?.id ?? null)); })
      .catch((e) => setErr((e as Error).message));
  }, [projectId]);

  /* ── editor + live collaboration ──────────────────────────────────── */
  useEffect(() => {
    teardown.current?.();
    teardown.current = null;
    setPeers([]);
    if (!fileId || !hostRef.current) return;

    let disposed = false;
    let ed: monaco.editor.IStandaloneCodeEditor | null = null;
    let ws: WebSocket | null = null;
    let doc: Y.Doc | null = null;
    let binding: MonacoBinding | null = null;
    let textTimer: number | undefined;

    (async () => {
      const file = await apiReadFile(fileId).catch(() => null);
      if (!file || disposed || !hostRef.current) return;

      const model = monaco.editor.createModel(file.content ?? "", file.language);
      ed = monaco.editor.create(hostRef.current, {
        model, theme: "eaios-dark", fontSize: 13, automaticLayout: true,
        minimap: { enabled: false }, scrollBeyondLastLine: false,
        padding: { top: 10 }, tabSize: 2, renderLineHighlight: "line",
      });
      edRef.current = ed;

      // Live mode only: the demo has no server to relay updates through.
      if (!live || !token) { setStatus("offline — changes save on ⌘S"); return; }

      doc = new Y.Doc();
      const ytext = doc.getText("monaco");
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(
        `${proto}://${window.location.host}/api/ws/collab/${fileId}?token=${encodeURIComponent(token)}`);
      ws.binaryType = "arraybuffer";

      ws.onopen = () => setStatus("live");
      ws.onclose = () => !disposed && setStatus("reconnecting…");
      ws.onerror = () => !disposed && setStatus("offline");

      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          Y.applyUpdate(doc!, new Uint8Array(ev.data), "remote");
          return;
        }
        try {
          const msg = JSON.parse(ev.data as string);
          if (msg.type === "collab.peers") setPeers(msg.peers || []);
          if (msg.type === "collab.init" && ytext.length === 0 && msg.content) {
            // First client in the room seeds the shared document from storage.
            doc!.transact(() => ytext.insert(0, msg.content), "seed");
          }
        } catch { /* ignore malformed control frames */ }
      };

      // Local edits → binary update on the wire.
      doc.on("update", (update: Uint8Array, origin: unknown) => {
        if (origin === "remote") return;
        if (ws?.readyState === WebSocket.OPEN) ws.send(update);
        // Report the resulting text so the server can persist it (debounced).
        window.clearTimeout(textTimer);
        textTimer = window.setTimeout(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "collab.text", content: ytext.toString() }));
          }
        }, 1200);
      });

      binding = new MonacoBinding(ytext, model, new Set([ed]));
    })();

    teardown.current = () => {
      disposed = true;
      window.clearTimeout(textTimer);
      binding?.destroy();
      ws?.close();
      doc?.destroy();
      ed?.getModel()?.dispose();
      ed?.dispose();
      edRef.current = null;
    };
    return () => { teardown.current?.(); teardown.current = null; };
  }, [fileId, live, token]);

  /* ── actions ──────────────────────────────────────────────────────── */
  async function save() {
    if (!fileId || !edRef.current) return;
    setBusy(true); setErr("");
    try {
      await apiSaveFile(fileId, edRef.current.getValue(), "manual save");
      setStatus("saved");
      setTimeout(() => setStatus(live ? "live" : "offline"), 1500);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); void save(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function newProject() {
    const name = window.prompt("Project name");
    if (!name?.trim()) return;
    try { const p = await apiCreateProject(name.trim()); setProjects((x) => [p, ...x]); setProjectId(p.id); }
    catch (e) { setErr((e as Error).message); }
  }

  async function newFile() {
    if (!projectId) return;
    const path = window.prompt("File path (e.g. src/main.py)");
    if (!path?.trim()) return;
    try {
      const f = await apiCreateFile(projectId, path.trim(), "");
      setFiles((x) => [...x, f].sort((a, b) => a.path.localeCompare(b.path)));
      setFileId(f.id);
    } catch (e) { setErr((e as Error).message); }
  }

  async function removeFile(id: string) {
    if (!window.confirm("Delete this file? Its history goes too.")) return;
    try {
      await apiDeleteFile(id);
      setFiles((x) => x.filter((f) => f.id !== id));
      if (fileId === id) setFileId(null);
    } catch (e) { setErr((e as Error).message); }
  }

  async function removeProject(id: string) {
    if (!window.confirm("Delete this project and every file in it?")) return;
    try {
      await apiDeleteProject(id);
      setProjects((x) => x.filter((p) => p.id !== id));
      if (projectId === id) { setProjectId(null); setFileId(null); }
    } catch (e) { setErr((e as Error).message); }
  }

  async function openVersions() {
    if (!fileId) return;
    setShowVersions(true);
    try { setVersions(await apiFileVersions(fileId)); } catch (e) { setErr((e as Error).message); }
  }

  async function restore(versionId: string) {
    if (!fileId) return;
    try {
      const f = await apiRestoreVersion(fileId, versionId);
      edRef.current?.setValue(f.content ?? "");
      setShowVersions(false);
    } catch (e) { setErr((e as Error).message); }
  }

  /* ── render ───────────────────────────────────────────────────────── */
  return (
    <div style={{ display: "flex", height: "100%", minHeight: 0 }}>
      {/* explorer */}
      <div style={{ width: 232, borderRight: "1px solid var(--line)", display: "flex",
                    flexDirection: "column", minHeight: 0 }}>
        <div style={{ padding: "8px 10px", display: "flex", alignItems: "center", gap: 6 }}>
          <Code2 size={14} aria-hidden />
          <b style={{ fontSize: 12, flex: 1 }}>Projects</b>
          <button className="btn sm" onClick={newProject} title="New project"><Plus size={12} /></button>
        </div>
        <div style={{ overflowY: "auto", paddingBottom: 6 }}>
          {projects.length === 0 && (
            <div className="faint" style={{ padding: "6px 12px", fontSize: 11.5 }}>
              No projects yet — create one.
            </div>
          )}
          {projects.map((p) => (
            <div key={p.id}>
              <div
                onClick={() => setProjectId(p.id === projectId ? null : p.id)}
                style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px",
                         cursor: "pointer", fontSize: 12,
                         background: p.id === projectId ? "rgba(34,211,238,.10)" : undefined }}
              >
                <ChevronRight size={12} aria-hidden
                  style={{ transform: p.id === projectId ? "rotate(90deg)" : "none", transition: "transform .12s" }} />
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {p.name}
                </span>
                <button className="btn sm ghost" title="Delete project"
                  onClick={(e) => { e.stopPropagation(); void removeProject(p.id); }}>
                  <Trash2 size={11} />
                </button>
              </div>
              {p.id === projectId && (
                <div style={{ paddingLeft: 8 }}>
                  {files.map((f) => (
                    <div key={f.id} onClick={() => setFileId(f.id)}
                      style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 10px 4px 16px",
                               cursor: "pointer", fontSize: 11.5,
                               background: f.id === fileId ? "rgba(34,211,238,.16)" : undefined }}>
                      <FileText size={11} className="faint" aria-hidden />
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {f.path}
                      </span>
                      <button className="btn sm ghost" title="Delete file"
                        onClick={(e) => { e.stopPropagation(); void removeFile(f.id); }}>
                        <Trash2 size={10} />
                      </button>
                    </div>
                  ))}
                  <button className="btn sm" style={{ margin: "4px 0 8px 16px" }} onClick={newFile}>
                    <FilePlus size={11} /> New file
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* editor */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
                      borderBottom: "1px solid var(--line)" }}>
          <span style={{ fontSize: 12, fontWeight: 600 }}>{activeFile?.path ?? "No file open"}</span>
          {status && (
            <span className="faint" style={{ fontSize: 10.5 }}>
              <span style={{ color: status === "live" ? "var(--ok, #34d399)" : undefined }}>●</span> {status}
            </span>
          )}
          <div style={{ flex: 1 }} />
          {peers.length > 0 && (
            <span title={peers.map((p) => p.name).join(", ")}
              style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
              <Users size={12} aria-hidden />
              {peers.slice(0, 4).map((p) => (
                <span key={p.user_id} className="avatar sm"
                  style={{ "--hue": p.hue } as React.CSSProperties}>
                  {p.name.split(" ").map((s) => s[0]).slice(0, 2).join("")}
                </span>
              ))}
              {peers.length > 4 && <span className="faint">+{peers.length - 4}</span>}
            </span>
          )}
          <button className="btn sm" onClick={openVersions} disabled={!fileId}>
            <History size={12} /> History
          </button>
          <button className="btn sm primary" onClick={save} disabled={!fileId || busy}>
            {busy ? <Loader2 size={12} className="spin" /> : <Save size={12} />} Save
          </button>
        </div>

        {err && <div className="banner error" style={{ fontSize: 11.5 }}>{err}</div>}

        <div ref={hostRef} style={{ flex: 1, minHeight: 0 }} />

        {!fileId && (
          <div className="empty" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
            <Code2 size={26} className="faint" aria-hidden />
            <div className="faint" style={{ fontSize: 12 }}>
              Pick a file, or create one. Open the same file in two windows to see live editing.
            </div>
          </div>
        )}
      </div>

      {/* version history */}
      {showVersions && (
        <div style={{ width: 250, borderLeft: "1px solid var(--line)", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "8px 10px", display: "flex", alignItems: "center", gap: 6 }}>
            <History size={13} aria-hidden />
            <b style={{ fontSize: 12, flex: 1 }}>History</b>
            <button className="btn sm ghost" onClick={() => setShowVersions(false)}>✕</button>
          </div>
          <div style={{ overflowY: "auto", padding: "0 8px 8px" }}>
            {versions.length === 0 && <div className="faint" style={{ fontSize: 11.5, padding: 6 }}>No saved versions yet.</div>}
            {versions.map((v) => (
              <div key={v.id} className="card" style={{ padding: 8, marginBottom: 6 }}>
                <div style={{ fontSize: 11, fontWeight: 600 }}>{v.note || "autosave"}</div>
                <div className="faint" style={{ fontSize: 10 }}>
                  {v.author_name || "—"} · {new Date(v.created_at).toLocaleString()} · {v.size} chars
                </div>
                <button className="btn sm" style={{ marginTop: 5 }} onClick={() => restore(v.id)}>Restore</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
