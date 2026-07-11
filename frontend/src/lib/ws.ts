/* Realtime client — presence + live agent feed over WebSocket.
   Live mode only; demo mode keeps its simulated feed. Auto-reconnects with
   backoff and keeps proxies alive with a ping every 25s. */
import { useOS } from "../store";
import type { FeedEvent, PresenceUser } from "../types";

let socket: WebSocket | null = null;
let pingTimer: number | null = null;
let retryTimer: number | null = null;
let retryDelay = 1000;
let wantOpen = false;

type WsEvent =
  | { type: "presence"; users: PresenceUser[] }
  | { type: "agent.step"; agent: string; status: "start" | "done"; task: string; user: string; confidence?: number }
  | { type: "chat.message"; conversation_id: string; user: string; agent: string; preview: string }
  | { type: "doc.status"; doc_id: string; title: string; status: string; chunks: number; entities: number }
  | { type: "workflow.run"; workflow: string; status: string; ms?: number }
  | { type: "workflow.notify"; workflow: string; message: string }
  | { type: "workflow.approval"; workflow: string; run_id: string; message: string }
  | { type: "typing"; user: string }
  | { type: "pong" };

const chatListeners = new Set<(convId: string) => void>();
export function onChatMessage(fn: (convId: string) => void): () => void {
  chatListeners.add(fn);
  return () => chatListeners.delete(fn);
}

function feedFrom(ev: WsEvent): Omit<FeedEvent, "id" | "time"> | null {
  switch (ev.type) {
    case "agent.step":
      return ev.status === "start"
        ? { agent: ev.agent, text: `started · ${ev.task}`, kind: "run" }
        : { agent: ev.agent, text: `done${ev.confidence ? ` · ${ev.confidence}% conf` : ""} · ${ev.task}`, kind: "run" };
    case "doc.status":
      return { agent: "indexer", text: `“${ev.title}” indexed — ${ev.chunks} chunks, ${ev.entities} entities`, kind: "index" };
    case "workflow.run":
      return { agent: "workflow", text: `${ev.workflow} — ${ev.status}${ev.ms ? ` in ${ev.ms}ms` : ""}`, kind: "system" };
    case "workflow.notify":
      return { agent: "notify", text: ev.message, kind: "system" };
    case "workflow.approval":
      return { agent: "approval", text: `⏸ ${ev.workflow} needs approval — ${ev.message}`, kind: "auth" };
    case "chat.message":
      return { agent: ev.agent || "chat", text: `${ev.user}: ${ev.preview}`, kind: "run" };
    default:
      return null;
  }
}

function handleMessage(raw: string) {
  let ev: WsEvent;
  try {
    ev = JSON.parse(raw);
  } catch {
    return;
  }
  const os = useOS.getState();
  if (ev.type === "presence") {
    os.setOnline(ev.users);
    return;
  }
  if (ev.type === "agent.step") {
    os.setAgentBusy(ev.status === "start");
  }
  if (ev.type === "chat.message") {
    chatListeners.forEach((fn) => fn(ev.conversation_id));
  }
  const item = feedFrom(ev);
  if (item) os.pushFeed(item);
}

export function connectRealtime(): void {
  const { live, token } = useOS.getState();
  if (!live || !token || socket) return;
  wantOpen = true;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/api/ws?token=${encodeURIComponent(token)}`);
  socket = ws;

  ws.onopen = () => {
    retryDelay = 1000;
    useOS.getState().setWsConnected(true);
    pingTimer = window.setInterval(() => ws.readyState === ws.OPEN && ws.send("ping"), 25000);
  };
  ws.onmessage = (e) => handleMessage(e.data);
  ws.onclose = () => {
    if (pingTimer) window.clearInterval(pingTimer);
    pingTimer = null;
    socket = null;
    const os = useOS.getState();
    os.setWsConnected(false);
    os.setOnline([]);
    if (wantOpen && os.live && os.token) {
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        connectRealtime();
      }, retryDelay);
      retryDelay = Math.min(retryDelay * 2, 15000);
    }
  };
  ws.onerror = () => ws.close();
}

export function disconnectRealtime(): void {
  wantOpen = false;
  if (retryTimer) window.clearTimeout(retryTimer);
  retryTimer = null;
  socket?.close();
  socket = null;
  useOS.getState().setWsConnected(false);
  useOS.getState().setOnline([]);
}
