/* First-run setup guide for a new company admin. After a company signs up,
   its admin gets a dismissible checklist that walks them through standing up
   their own K-OS: invite the team, add knowledge, connect tools, try the AI,
   install the app. Progress + dismissal persist per workspace (localStorage).
   Reopen any time from Settings → "Open setup guide". */
import { BookOpen, CheckCircle2, Download, MessageSquare, Plug, Rocket, Users, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { canInstall, isStandalone, promptInstall } from "../lib/pwa";
import { useOS } from "../store";
import type { AppId } from "../types";

type Step = { key: string; icon: JSX.Element; title: string; text: string; cta: string; app?: AppId; install?: boolean };

const STEPS: Step[] = [
  { key: "team", icon: <Users size={16} />, title: "Invite your team", app: "admin",
    text: "Open the Admin console to add managers, HR and employees — set each person's email and a starter password, then share it with them.", cta: "Open Admin" },
  { key: "knowledge", icon: <BookOpen size={16} />, title: "Add your company knowledge", app: "knowledge",
    text: "Upload PDFs, Word docs or spreadsheets. Everything is indexed privately to your workspace so the AI can answer from it with citations.", cta: "Open Knowledge" },
  { key: "connect", icon: <Plug size={16} />, title: "Connect your tools", app: "connectors",
    text: "Sync Gmail, Google Drive or an entire website into your knowledge base so answers stay current — no manual uploads.", cta: "Open Connectors" },
  { key: "chat", icon: <MessageSquare size={16} />, title: "Ask your first question", app: "chat",
    text: "Ask anything about what you uploaded. Answers come back with sources, a confidence score, and the agents that ran.", cta: "Open AI Chat" },
  { key: "install", icon: <Download size={16} />, title: "Install as a desktop app", install: true,
    text: "Install K-OS so your team opens it like any native app — no browser tab, launches straight to sign-in.", cta: "Install app" },
];

function keyFor(org: string | null) {
  return `eaios-setup:${org || "workspace"}`;
}

export default function SetupGuide() {
  const { user, orgName, open } = useOS();
  const isAdmin = user?.role === "admin";
  const storeKey = useMemo(() => keyFor(orgName), [orgName]);

  const [dismissed, setDismissed] = useState(true);
  const [done, setDone] = useState<Record<string, boolean>>({});

  // Load persisted state whenever the workspace changes; force-open on demand.
  useEffect(() => {
    const load = () => {
      try {
        const raw = JSON.parse(localStorage.getItem(storeKey) || "{}");
        setDone(raw.done || {});
        setDismissed(raw.dismissed === true);
      } catch { setDone({}); setDismissed(false); }
    };
    load();
    const onOpen = () => { setDismissed(false); };
    window.addEventListener("k-os:open-setup", onOpen);
    return () => window.removeEventListener("k-os:open-setup", onOpen);
  }, [storeKey]);

  function persist(next: { done?: Record<string, boolean>; dismissed?: boolean }) {
    const merged = { done, dismissed, ...next };
    try { localStorage.setItem(storeKey, JSON.stringify(merged)); } catch { /* private mode */ }
  }

  const steps = STEPS.filter((s) => !(s.install && isStandalone()));
  const completed = steps.filter((s) => done[s.key]).length;

  function complete(s: Step) {
    const nd = { ...done, [s.key]: true };
    setDone(nd);
    persist({ done: nd });
  }

  async function act(s: Step) {
    if (s.install) { if (canInstall()) await promptInstall(); }
    else if (s.app) open(s.app);
    complete(s);
  }

  function close() {
    setDismissed(true);
    persist({ dismissed: true });
  }

  if (!isAdmin || dismissed) return null;

  const allDone = completed === steps.length;

  return (
    <div className="setup-guide card" role="dialog" aria-label="Workspace setup guide">
      <div className="sg-head">
        <span className="sg-badge"><Rocket size={15} /></span>
        <div style={{ minWidth: 0 }}>
          <div className="sg-title">Set up {orgName || "your workspace"}</div>
          <div className="faint" style={{ fontSize: 11 }}>{completed} of {steps.length} done — you're the admin here</div>
        </div>
        <button className="sg-x" onClick={close} aria-label="Dismiss setup guide"><X size={15} /></button>
      </div>

      <div className="sg-bar"><span style={{ width: `${(completed / steps.length) * 100}%` }} /></div>

      <div className="sg-steps">
        {steps.map((s) => {
          const ok = !!done[s.key];
          return (
            <div key={s.key} className={`sg-step ${ok ? "ok" : ""}`}>
              <span className="sg-ico">{ok ? <CheckCircle2 size={16} /> : s.icon}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div className="sg-step-title">{s.title}</div>
                <div className="sg-step-text">{s.text}</div>
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button className={`btn sm ${ok ? "" : "primary"}`} onClick={() => act(s)}>{s.cta}</button>
                  {!ok && <button className="btn sm ghost" onClick={() => complete(s)}>Mark done</button>}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {allDone && (
        <div className="sg-foot">🎉 Your workspace is ready. <button className="link-btn" onClick={close}>Close guide</button></div>
      )}
    </div>
  );
}
