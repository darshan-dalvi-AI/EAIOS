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
 *
 * Running code happens in a sandboxed iframe with an opaque origin, never on
 * the server and never in this document — see lib/runCode.ts.
 */
import {
  ChevronRight, Code2, FilePlus, FileText, GitBranch as GitBranchIcon, GitCommitVertical, History,
  FolderUp, Loader2, Play, Plus, Save, Sparkles, Square, Terminal, Trash2, Upload, Users, X,
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
  apiCodeAssist, apiCreateFile, apiCreateProject, apiDeleteFile, apiDeleteProject,
  apiFileVersions, apiGitBranches, apiGitCheckout, apiGitCommit, apiGitCommitDetail,
  apiGitCreateBranch, apiGitHistory, apiGitStatus, apiGitWorkingDiff,
  apiImportFiles, apiProjectFiles, apiProjects, apiReadFile, apiRestoreVersion, apiSaveFile,
} from "../lib/api";
import { filesFromDrop, prepareImport, type Skipped } from "../lib/importFiles";
import { disposeSandbox, runCode, runtimeFor, stopCode } from "../lib/runCode";
import { useOS } from "../store";
import type {
  CodeFile, CodeProject, CollabPeer, FileVersionInfo,
  GitBranch as GitBranchInfo, GitCommit, GitDiffFile, GitStatus,
} from "../types";

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
  // ── source control ──
  const [showGit, setShowGit] = useState(false);
  const [branch, setBranch] = useState("main");
  const [branches, setBranches] = useState<GitBranchInfo[]>([]);
  const [gitStatus, setGitStatus] = useState<GitStatus | null>(null);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [commitMsg, setCommitMsg] = useState("");
  const [diff, setDiff] = useState<{ title: string; files: GitDiffFile[] } | null>(null);
  // ── editor tabs: the files currently open, in the order they were opened ──
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  // ── importing files and folders ──
  const [importing, setImporting] = useState("");                 // progress line
  const [dragging, setDragging] = useState(false);
  const [importReport, setImportReport] =
    useState<{ name: string; imported: number; skipped: Skipped[]; total: number } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const dirInput = useRef<HTMLInputElement>(null);
  // ── output console ──
  const [showOut, setShowOut] = useState(false);
  const [running, setRunning] = useState(false);
  const [runLine, setRunLine] = useState("");          // "Loading runtime…" etc.
  const [out, setOut] = useState<{ stream: "stdout" | "stderr"; text: string }[]>([]);
  const [lastRun, setLastRun] = useState<{ ok: boolean; ms: number } | null>(null);
  // ── AI assistant ──
  const [showAI, setShowAI] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiOut, setAiOut] = useState<{ action: string; answer: string; degraded?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [err, setErr] = useState("");

  const hostRef = useRef<HTMLDivElement>(null);
  const edRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const teardown = useRef<(() => void) | null>(null);
  const outRef = useRef<HTMLDivElement>(null);

  const activeFile = files.find((f) => f.id === fileId) || null;
  const runtime = runtimeFor(activeFile?.language);

  /* ── running the code ─────────────────────────────────────────────────
   * Nothing here executes anything. The text goes to a sandboxed iframe with
   * an opaque origin (lib/runCode.ts) and only its printed output comes back.
   * The editor's live text is used rather than the saved file, so you can try
   * a change without committing to it first. */
  async function run() {
    if (!runtime || running) return;
    const code = edRef.current?.getValue() ?? "";
    setOut([]); setLastRun(null); setRunning(true); setShowOut(true); setErr("");
    setRunLine(runtime === "python" ? "Starting Python…" : "Running…");
    try {
      await runCode(runtime, code, (e) => {

        if (e.type === "out") {
          setOut((prev) => {
            const next = [...prev, { stream: e.stream ?? "stdout", text: e.text ?? "" }];
            // A print-in-a-loop can emit thousands of chunks; React does not
            // need to hold all of them to show the person what happened.
            return next.length > 2000 ? next.slice(next.length - 2000) : next;
          });
        } else if (e.type === "status") {
          setRunLine(e.text ?? "");
        } else if (e.type === "done") {
          setLastRun({ ok: !!e.ok, ms: e.ms ?? 0 });
          setRunLine("");
        }
      }, activeFile?.path ?? "");
    } catch (e) {
      setErr((e as Error).message);
    } finally { setRunning(false); }
  }

  // Follow the output as it arrives, the way a terminal does.
  useEffect(() => {
    const el = outRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [out, runLine]);

  // A warm Pyodide holds ~100 MB. Give it back when the window closes.
  useEffect(() => disposeSandbox, []);

  // Opening a file adds a tab; tabs never reorder underneath the user.
  useEffect(() => {
    if (!fileId) return;
    setOpenTabs((t) => (t.includes(fileId) ? t : [...t, fileId]));
  }, [fileId]);

  // Drop tabs for files that no longer exist (deleted, or project switched).
  useEffect(() => {
    const ids = new Set(files.map((f) => f.id));
    setOpenTabs((t) => t.filter((id) => ids.has(id)));
  }, [files]);

  function closeTab(id: string) {
    setOpenTabs((t) => {
      const next = t.filter((x) => x !== id);
      if (id === fileId) setFileId(next[next.length - 1] ?? null);
      return next;
    });
  }

  /* ── importing ────────────────────────────────────────────────────────
   * `intoCurrent` is what separates "upload a file" from "open a folder".
   * Loose files land in the project you are already in — that is what picking
   * a file means. A folder becomes a project of its own, named after itself,
   * the way opening a folder works in every editor. */
  async function importSelection(picked: FileList | File[], intoCurrent: boolean) {
    const list = Array.from(picked);
    if (list.length === 0) return;
    setErr(""); setImportReport(null);
    setImporting(`Reading ${list.length} file${list.length === 1 ? "" : "s"}…`);
    try {
      const { files, skipped, rootName } = await prepareImport(list, (done, total) => {
        if (total > 20) setImporting(`Reading ${done} of ${total}…`);
      });
      if (files.length === 0) {
        setErr(skipped.length
          ? "Nothing importable there — it was all dependencies, build output or binaries."
          : "No files selected.");
        return;
      }
      setImporting(`Uploading ${files.length} file${files.length === 1 ? "" : "s"}…`);
      const target = intoCurrent && projectId ? { projectId } : { name: rootName || "Imported" };
      const r = await apiImportFiles(files, target);

      await loadProjects();
      setProjectId(r.project.id);
      const fresh = await apiProjectFiles(r.project.id);
      setFiles(fresh);
      // Open something immediately — an import that lands you on an empty
      // editor looks like it failed.
      const first = fresh.find((f) => files.some((n) => n.path === f.path)) ?? fresh[0];
      if (first) setFileId(first.id);

      setImportReport({
        name: r.project.name,
        imported: r.imported,
        // The server filters again, so its skip list is the authoritative one;
        // merge in what we dropped before uploading.
        skipped: [...skipped, ...r.skipped].slice(0, 60),
        total: skipped.length + r.skipped_total,
      });
    } catch (e) {
      setErr((e as Error).message);
    } finally { setImporting(""); }
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const dropped = await filesFromDrop(e.dataTransfer);
    // A dropped folder becomes its own project; dropped loose files join the
    // project already open.
    const isFolder = dropped.some((f) =>
      ((f as File & { webkitRelativePath?: string }).webkitRelativePath ?? "").includes("/"));
    await importSelection(dropped, !isFolder);
  }

  async function runAssist(action: "explain" | "fix" | "test" | "document" | "refactor") {
    if (!fileId) return;
    setAiBusy(true); setAiOut(null); setErr("");
    try {
      const sel = edRef.current?.getModel()?.getValueInRange(
        edRef.current.getSelection() ?? new monaco.Range(1, 1, 1, 1)) ?? "";
      const r = await apiCodeAssist(fileId, action, sel);
      setAiOut({ action: r.action, answer: r.answer, degraded: r.degraded });
    } catch (e) { setErr((e as Error).message); } finally { setAiBusy(false); }
  }

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
      // Ctrl/⌘+Enter runs — the binding every notebook and REPL already uses,
      // so nobody has to learn it. This effect has no dependency array, so the
      // handler always closes over the current file and run state.
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); void run(); }
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

  /* ── source control ─────────────────────────────────────────────── */
  const refreshGit = useCallback(async () => {
    if (!projectId) return;
    try {
      const [st, hist, brs] = await Promise.all([
        apiGitStatus(projectId, branch),
        apiGitHistory(projectId, branch),
        apiGitBranches(projectId),
      ]);
      setGitStatus(st); setCommits(hist); setBranches(brs);
    } catch (e) { setErr((e as Error).message); }
  }, [projectId, branch]);

  useEffect(() => { if (showGit) void refreshGit(); }, [showGit, refreshGit]);

  async function doCommit() {
    if (!projectId || !commitMsg.trim()) return;
    setBusy(true); setErr("");
    try {
      // Commit what is on the server, so flush the editor first.
      if (fileId && edRef.current) await apiSaveFile(fileId, edRef.current.getValue(), "before commit");
      await apiGitCommit(projectId, commitMsg.trim(), branch);
      setCommitMsg("");
      await refreshGit();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  async function showWorkingDiff() {
    if (!projectId) return;
    try {
      const d = await apiGitWorkingDiff(projectId, branch);
      setDiff({ title: "Uncommitted changes", files: d.files });
    } catch (e) { setErr((e as Error).message); }
  }

  async function showCommitDiff(cm: GitCommit) {
    if (!projectId) return;
    try {
      const d = await apiGitCommitDetail(projectId, cm.id);
      setDiff({ title: `${cm.short} · ${cm.message}`, files: d.diff });
    } catch (e) { setErr((e as Error).message); }
  }

  async function restoreCommit(cm: GitCommit) {
    if (!projectId) return;
    if (!window.confirm(`Restore every file to ${cm.short}? Uncommitted work is auto-saved to a rescue branch first.`)) return;
    setBusy(true);
    try {
      const r = await apiGitCheckout(projectId, cm.id);
      const fresh = await apiProjectFiles(projectId);
      setFiles(fresh);
      setFileId(fresh[0]?.id ?? null);
      await refreshGit();
      if (r.rescued_to) setErr(`Restored. Your uncommitted work was saved to branch "${r.rescued_to}".`);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  async function newBranch() {
    if (!projectId) return;
    const name = window.prompt("New branch name", "feature-1");
    if (!name?.trim()) return;
    try {
      await apiGitCreateBranch(projectId, name.trim(), branch);
      setBranch(name.trim());
      await refreshGit();
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
  /* The three panes carry class names purely so the phone stylesheet can reach
     them. Their widths are inline (232px explorer, 250px history), and an
     inline style beats any stylesheet rule that is not !important — which is
     why this layout survived every responsive pass and still put a 708px row
     inside a 396px window on a phone, stranding the editor off-screen with
     nothing to scroll. See the .code-explorer block in system.css. */
  return (
    <div className="code-root"
         style={{ display: "flex", height: "100%", minHeight: 0, position: "relative" }}
         onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
         onDragLeave={(e) => { if (e.currentTarget === e.target) setDragging(false); }}
         onDrop={(e) => { void onDrop(e); }}>

      {dragging && (
        <div style={{ position: "absolute", inset: 0, zIndex: 20, display: "flex",
                      alignItems: "center", justifyContent: "center", flexDirection: "column",
                      gap: 8, background: "rgba(10,16,24,.86)",
                      border: "2px dashed var(--accent)", borderRadius: 8, pointerEvents: "none" }}>
          <FolderUp size={26} aria-hidden />
          <b style={{ fontSize: 13 }}>Drop files or a folder to import</b>
          <span className="faint" style={{ fontSize: 11 }}>
            A folder becomes its own project · dependencies and binaries are skipped
          </span>
        </div>
      )}
      {/* explorer */}
      <div className="code-explorer"
           style={{ width: 232, borderRight: "1px solid var(--line)", display: "flex",
                    flexDirection: "column", minHeight: 0 }}>
        <div style={{ padding: "8px 10px", display: "flex", alignItems: "center", gap: 6 }}>
          <Code2 size={14} aria-hidden />
          <b style={{ fontSize: 12, flex: 1 }}>Projects</b>
          <button className="btn sm" onClick={() => fileInput.current?.click()}
                  disabled={!!importing}
                  title={projectId ? "Upload files into this project" : "Upload files"}>
            <Upload size={12} />
          </button>
          <button className="btn sm" onClick={() => dirInput.current?.click()}
                  disabled={!!importing} title="Open a folder as a new project">
            <FolderUp size={12} />
          </button>
          <button className="btn sm" onClick={newProject} title="New project"><Plus size={12} /></button>
        </div>

        {/* Hidden pickers. `webkitdirectory` is the only way to let someone
            choose a whole folder; it is non-standard but implemented by every
            current browser, and the button simply does nothing without it. */}
        <input ref={fileInput} type="file" multiple hidden
               onChange={(e) => { void importSelection(e.target.files ?? [], true); e.target.value = ""; }} />
        <input ref={dirInput} type="file" hidden
               // @ts-expect-error — non-standard, but this is how folder pick works
               webkitdirectory="" directory=""
               onChange={(e) => { void importSelection(e.target.files ?? [], false); e.target.value = ""; }} />

        {importing && (
          <div className="faint" style={{ padding: "0 12px 6px", fontSize: 11,
                                          display: "flex", alignItems: "center", gap: 5 }}>
            <Loader2 size={11} className="spin" /> {importing}
          </div>
        )}
        <div style={{ overflowY: "auto", paddingBottom: 6 }}>
          {projects.length === 0 && (
            <div className="faint" style={{ padding: "6px 12px", fontSize: 11.5, lineHeight: 1.6 }}>
              No projects yet — create one, open a folder, or drag one in.
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
      <div className="code-main"
           style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
        <div className="code-toolbar"
             style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
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
          {running ? (
            <button className="btn sm" onClick={stopCode} title="Stop the running program">
              <Square size={11} /> Stop
            </button>
          ) : (
            <button className="btn sm" onClick={run} disabled={!runtime}
                    title={runtime
                      ? `Run this ${runtime === "python" ? "Python" : "JavaScript"} file in your browser`
                      : "Only Python and JavaScript files can be run"}>
              <Play size={12} /> Run
            </button>
          )}
          <button className={`btn sm ${showOut ? "primary" : ""}`}
                  onClick={() => setShowOut((v) => !v)} title="Output console">
            <Terminal size={12} /> Output
          </button>
          <button className={`btn sm ${showAI ? "primary" : ""}`}
                  onClick={() => setShowAI((v) => !v)} disabled={!fileId} title="AI assistant">
            <Sparkles size={12} /> AI
          </button>
          <button className={`btn sm ${showGit ? "primary" : ""}`}
                  onClick={() => { setShowGit((v) => !v); setDiff(null); }}
                  disabled={!projectId} title="Source control">
            <GitBranchIcon size={12} /> Git
            {gitStatus && !gitStatus.clean && (
              <span style={{ marginLeft: 4, color: "var(--warn, #f59e0b)" }}>●</span>
            )}
          </button>
          <button className="btn sm" onClick={openVersions} disabled={!fileId}>
            <History size={12} /> History
          </button>
          <button className="btn sm primary" onClick={save} disabled={!fileId || busy}>
            {busy ? <Loader2 size={12} className="spin" /> : <Save size={12} />} Save
          </button>
        </div>

        {err && <div className="banner error" style={{ fontSize: 11.5 }}>{err}</div>}

        {importReport && (
          <div className="banner" style={{ fontSize: 11.5, display: "flex", gap: 8,
                                           alignItems: "flex-start" }}>
            <div style={{ flex: 1 }}>
              <b>{importReport.imported} file{importReport.imported === 1 ? "" : "s"}</b>
              {" imported into "}<b>{importReport.name}</b>
              {importReport.total > 0 && <> · {importReport.total} skipped</>}
              {importReport.total > 0 && (
                <details style={{ marginTop: 4 }}>
                  <summary style={{ cursor: "pointer" }}>What was skipped, and why</summary>
                  <div style={{ maxHeight: 128, overflowY: "auto", marginTop: 4,
                                fontFamily: "var(--mono, ui-monospace, monospace)", fontSize: 10.5 }}>
                    {importReport.skipped.map((s, i) => (
                      <div key={i} style={{ display: "flex", gap: 8 }}>
                        <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis",
                                       whiteSpace: "nowrap" }}>{s.path}</span>
                        <span className="faint">{s.reason}</span>
                      </div>
                    ))}
                    {importReport.total > importReport.skipped.length && (
                      <div className="faint">
                        …and {importReport.total - importReport.skipped.length} more
                      </div>
                    )}
                  </div>
                </details>
              )}
            </div>
            <button className="btn sm ghost" onClick={() => setImportReport(null)}
                    aria-label="Dismiss import summary">✕</button>
          </div>
        )}

        {/* open files, as tabs */}
        {openTabs.length > 0 && (
          <div style={{ display: "flex", gap: 1, overflowX: "auto", borderBottom: "1px solid var(--line)",
                        background: "rgba(255,255,255,.02)" }} role="tablist" aria-label="Open files">
            {openTabs.map((id) => {
              const f = files.find((x) => x.id === id);
              if (!f) return null;
              const active = id === fileId;
              return (
                <div key={id} role="tab" aria-selected={active}
                     onClick={() => setFileId(id)}
                     style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 8px",
                              fontSize: 11.5, cursor: "pointer", whiteSpace: "nowrap",
                              borderTop: active ? "2px solid var(--accent)" : "2px solid transparent",
                              background: active ? "rgba(34,211,238,.10)" : undefined }}>
                  <FileText size={10} className="faint" aria-hidden />
                  {f.path.split("/").pop()}
                  <button className="btn sm ghost" style={{ padding: 1 }} aria-label={`Close ${f.path}`}
                          onClick={(e) => { e.stopPropagation(); closeTab(id); }}>
                    <X size={9} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* editor above, output below — the side panels stay full height */}
          <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <div ref={hostRef} style={{ flex: 1, minWidth: 0, minHeight: 0 }} />

            {showOut && (
              <div style={{ height: 200, borderTop: "1px solid var(--line)", display: "flex",
                            flexDirection: "column", minHeight: 0, background: "#0a1018" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 10px",
                              borderBottom: "1px solid var(--line)" }}>
                  <Terminal size={12} aria-hidden />
                  <b style={{ fontSize: 11.5 }}>Output</b>
                  {running && (
                    <span className="faint" style={{ fontSize: 10.5, display: "flex",
                                                     alignItems: "center", gap: 5 }}>
                      <Loader2 size={11} className="spin" /> {runLine || "Running…"}
                    </span>
                  )}
                  {!running && lastRun && (
                    <span style={{ fontSize: 10.5,
                                   color: lastRun.ok ? "var(--ok, #34d399)" : "var(--bad, #f87171)" }}>
                      {lastRun.ok ? "Finished" : "Failed"} in {lastRun.ms} ms
                    </span>
                  )}
                  <div style={{ flex: 1 }} />
                  <span className="faint" style={{ fontSize: 10 }}
                        title="Your code runs in a sandboxed frame in this browser — never on the server, and with no access to your session.">
                    sandboxed in your browser
                  </span>
                  <button className="btn sm ghost" onClick={() => { setOut([]); setLastRun(null); }}
                          disabled={running || out.length === 0}>Clear</button>
                  <button className="btn sm ghost" onClick={() => setShowOut(false)}
                          aria-label="Close output">✕</button>
                </div>
                <div ref={outRef} role="log" aria-live="polite" aria-label="Program output"
                     style={{ flex: 1, overflowY: "auto", padding: "8px 10px", fontSize: 11.5,
                              fontFamily: "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)",
                              whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.5 }}>
                  {out.length === 0 && !running && (
                    <span className="faint">
                      {runtime === "python" ? (
                        <>Press Run. Python 3.13 with 340+ packages (numpy, pandas, …) —
                          {" "}<code>import</code> installs them automatically. The first run
                          downloads the runtime; later ones are instant.
                          {"\n"}No network and no file access from inside the sandbox, so
                          {" "}<code>requests</code> and <code>open()</code> will not work.</>
                      ) : runtime === "javascript" ? (
                        <>Press Run. Top-level <code>await</code> works. No network and no
                          {" "}DOM from inside the sandbox.</>
                      ) : (
                        <>Open a <code>.py</code> or <code>.js</code> file to run it.</>
                      )}
                    </span>
                  )}
                  {out.map((chunk, i) => (
                    <span key={i} style={{ color: chunk.stream === "stderr" ? "#f87171" : undefined }}>
                      {chunk.text}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* AI assistant */}
          {showAI && (
            <div style={{ width: 300, borderLeft: "1px solid var(--line)", display: "flex",
                          flexDirection: "column", minHeight: 0 }}>
              <div style={{ padding: "8px 10px", display: "flex", alignItems: "center", gap: 6 }}>
                <Sparkles size={13} aria-hidden />
                <b style={{ fontSize: 12, flex: 1 }}>AI assistant</b>
                <button className="btn sm ghost" onClick={() => setShowAI(false)} aria-label="Close AI assistant">✕</button>
              </div>
              <div className="faint" style={{ fontSize: 10.5, padding: "0 10px 8px" }}>
                Works on your selection, or the whole file if nothing is selected.
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, padding: "0 10px 8px" }}>
                {([["explain", "Explain"], ["fix", "Find bugs"], ["test", "Write tests"],
                   ["document", "Document"], ["refactor", "Refactor"]] as const).map(([id, label]) => (
                  <button key={id} className="btn sm" disabled={aiBusy}
                          onClick={() => runAssist(id)}>{label}</button>
                ))}
              </div>
              <div style={{ overflowY: "auto", padding: "0 10px 10px", flex: 1 }}>
                {aiBusy && (
                  <div className="faint" style={{ fontSize: 11.5, display: "flex", gap: 6, alignItems: "center" }}>
                    <Loader2 size={12} className="spin" /> Thinking…
                  </div>
                )}
                {aiOut && !aiBusy && (
                  <>
                    {aiOut.degraded && (
                      <div className="banner" style={{ fontSize: 10.5, marginBottom: 6 }}>
                        The model was unreachable — this is a reduced answer.
                      </div>
                    )}
                    <div style={{ fontSize: 11.5, whiteSpace: "pre-wrap", lineHeight: 1.55 }}>
                      {aiOut.answer}
                    </div>
                    <button className="btn sm" style={{ marginTop: 8 }}
                            onClick={() => navigator.clipboard?.writeText(aiOut.answer)}>
                      Copy
                    </button>
                  </>
                )}
                {!aiBusy && !aiOut && (
                  <div className="faint" style={{ fontSize: 11 }}>
                    Pick an action above. Answers come from the same model and daily budget as the rest of the workspace.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {!fileId && (
          <div className="empty" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
            <Code2 size={26} className="faint" aria-hidden />
            <div className="faint" style={{ fontSize: 12 }}>
              Pick a file, or create one. Open the same file in two windows to see live editing.
            </div>
          </div>
        )}
      </div>

      {/* source control */}
      {showGit && (
        <div style={{ width: 300, borderLeft: "1px solid var(--line)", display: "flex",
                      flexDirection: "column", minHeight: 0 }}>
          <div style={{ padding: "8px 10px", display: "flex", alignItems: "center", gap: 6 }}>
            <GitBranchIcon size={13} aria-hidden />
            <b style={{ fontSize: 12, flex: 1 }}>Source Control</b>
            <button className="btn sm ghost" onClick={() => setShowGit(false)} aria-label="Close source control">✕</button>
          </div>

          {/* branch */}
          <div style={{ display: "flex", gap: 5, padding: "0 10px 8px" }}>
            <select className="input sm" value={branch} style={{ flex: 1, fontSize: 11.5 }}
                    onChange={(e) => setBranch(e.target.value)} aria-label="Branch">
              {branches.map((b) => (
                <option key={b.name} value={b.name}>{b.name} ({b.commits})</option>
              ))}
            </select>
            <button className="btn sm" onClick={newBranch} title="New branch">
              <Plus size={11} />
            </button>
          </div>

          {/* changes + commit */}
          <div style={{ padding: "0 10px 8px", borderBottom: "1px solid var(--line)" }}>
            {gitStatus?.clean ? (
              <div className="faint" style={{ fontSize: 11.5, padding: "4px 0 8px" }}>
                No changes — the working tree matches {gitStatus.head ? gitStatus.head.slice(0, 8) : "the branch"}.
              </div>
            ) : (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 6, margin: "2px 0 6px" }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600 }}>Changes</span>
                  <button className="btn sm ghost" style={{ fontSize: 10.5 }} onClick={showWorkingDiff}>
                    view diff
                  </button>
                </div>
                {(["added", "modified", "removed"] as const).map((k) =>
                  (gitStatus?.[k] ?? []).map((path) => (
                    <div key={k + path} style={{ display: "flex", gap: 6, fontSize: 11, padding: "1px 0" }}>
                      <span style={{ width: 12, fontWeight: 700,
                        color: k === "added" ? "#34d399" : k === "removed" ? "#f87171" : "#fbbf24" }}>
                        {k === "added" ? "A" : k === "removed" ? "D" : "M"}
                      </span>
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{path}</span>
                    </div>
                  )))}
                <input className="input sm" style={{ width: "100%", marginTop: 7, fontSize: 11.5 }}
                       placeholder="Commit message" value={commitMsg}
                       onChange={(e) => setCommitMsg(e.target.value)}
                       onKeyDown={(e) => { if (e.key === "Enter") void doCommit(); }}
                       aria-label="Commit message" />
                <button className="btn sm primary" style={{ width: "100%", marginTop: 5, justifyContent: "center" }}
                        onClick={doCommit} disabled={busy || !commitMsg.trim()}>
                  {busy ? <Loader2 size={11} className="spin" /> : <GitCommitVertical size={11} />} Commit
                </button>
              </>
            )}
          </div>

          {/* history */}
          <div style={{ overflowY: "auto", padding: "8px 10px" }}>
            <div style={{ fontSize: 11.5, fontWeight: 600, marginBottom: 5 }}>History</div>
            {commits.length === 0 && (
              <div className="faint" style={{ fontSize: 11 }}>No commits on this branch yet.</div>
            )}
            {commits.map((cm) => (
              <div key={cm.id} className="card" style={{ padding: 7, marginBottom: 5 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <code style={{ fontSize: 10, color: "var(--accent)" }}>{cm.short}</code>
                  <span style={{ fontSize: 11, flex: 1, overflow: "hidden",
                                 textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{cm.message}</span>
                </div>
                <div className="faint" style={{ fontSize: 9.5, marginTop: 2 }}>
                  {cm.author_name} · {new Date(cm.created_at).toLocaleString()} · {cm.file_count} files
                </div>
                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                  <button className="btn sm ghost" style={{ fontSize: 10 }}
                          onClick={() => showCommitDiff(cm)}>diff</button>
                  <button className="btn sm ghost" style={{ fontSize: 10 }}
                          onClick={() => restoreCommit(cm)}>restore</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* diff viewer */}
      {diff && (
        <div style={{ position: "absolute", inset: 0, background: "var(--bg)", zIndex: 5,
                      display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px",
                        borderBottom: "1px solid var(--line)" }}>
            <b style={{ fontSize: 12 }}>{diff.title}</b>
            <div style={{ flex: 1 }} />
            <button className="btn sm" onClick={() => setDiff(null)}>Close</button>
          </div>
          <div style={{ overflow: "auto", padding: 10, fontFamily: "monospace", fontSize: 11.5 }}>
            {diff.files.length === 0 && <div className="faint">No differences.</div>}
            {diff.files.map((f) => (
              <div key={f.path} style={{ marginBottom: 14 }}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>
                  {f.path} <span className="faint" style={{ fontWeight: 400 }}>({f.change})</span>
                </div>
                {f.patch.split("\n").map((line, i) => {
                  const add = line.startsWith("+") && !line.startsWith("+++");
                  const del = line.startsWith("-") && !line.startsWith("---");
                  const hunk = line.startsWith("@@");
                  return (
                    <div key={i} style={{
                      whiteSpace: "pre-wrap", padding: "0 4px",
                      background: add ? "rgba(52,211,153,.14)" : del ? "rgba(248,113,113,.14)" : undefined,
                      color: hunk ? "var(--accent)" : undefined,
                    }}>{line || " "}</div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* version history */}
      {showVersions && (
        <div className="code-history"
             style={{ width: 250, borderLeft: "1px solid var(--line)", display: "flex", flexDirection: "column" }}>
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
