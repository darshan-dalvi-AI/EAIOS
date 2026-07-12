/* Toast notifications — transient popups for new live-feed events
   (workflow results, approvals, security flags, system notices).
   Complements the MenuBar bell: toasts for the moment, bell for history. */
import { Bell, ShieldAlert, Workflow as WorkflowIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useOS } from "../store";
import type { FeedEvent } from "../types";

const TOAST_KINDS = new Set(["system", "auth"]); // notify results, approvals, security, resilience notices
const TTL_MS = 5000;

export default function Toasts() {
  const liveFeed = useOS((s) => s.liveFeed);
  const [toasts, setToasts] = useState<FeedEvent[]>([]);
  const seen = useRef<Set<number>>(new Set());
  const booted = useRef(false);

  useEffect(() => {
    if (!booted.current) {
      // don't replay history on mount — only toast events that arrive live
      liveFeed.forEach((e) => seen.current.add(e.id));
      booted.current = true;
      return;
    }
    const fresh = liveFeed.filter((e) => !seen.current.has(e.id) && TOAST_KINDS.has(e.kind));
    liveFeed.forEach((e) => seen.current.add(e.id));
    if (!fresh.length) return;
    setToasts((t) => [...fresh, ...t].slice(0, 3));
    fresh.forEach((e) =>
      window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== e.id)), TTL_MS),
    );
  }, [liveFeed]);

  if (!toasts.length) return null;
  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {toasts.map((t) => (
        <button key={t.id} className="toast" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>
          {t.kind === "auth" ? <ShieldAlert size={14} style={{ color: "var(--warn)" }} />
            : t.agent === "workflow" || t.agent === "notify" ? <WorkflowIcon size={14} style={{ color: "var(--accent)" }} />
            : <Bell size={14} style={{ color: "var(--accent)" }} />}
          <span className="toast-body">
            <b>{t.agent}</b>
            <span>{t.text}</span>
          </span>
          <span className="faint" style={{ fontSize: 10 }}>{t.time}</span>
        </button>
      ))}
    </div>
  );
}
