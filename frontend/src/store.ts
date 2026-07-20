import { create } from "zustand";
import type { AppId, FeedEvent, PresenceUser, Rect, SessionUser, Win } from "./types";

const SIZES: Record<AppId, { w: number; h: number }> = {
  chat: { w: 860, h: 600 },
  knowledge: { w: 900, h: 620 },
  agents: { w: 940, h: 620 },
  graph: { w: 960, h: 640 },
  automations: { w: 980, h: 640 },
  traces: { w: 940, h: 620 },
  sql: { w: 900, h: 600 },
  search: { w: 880, h: 620 },
  tasks: { w: 980, h: 620 },
  analytics: { w: 920, h: 640 },
  dashboards: { w: 960, h: 660 },
  studio: { w: 940, h: 640 },
  connectors: { w: 900, h: 600 },
  meeting: { w: 900, h: 620 },
  video: { w: 980, h: 660 },
  admin: { w: 880, h: 600 },
  terminal: { w: 660, h: 440 },
  settings: { w: 680, h: 540 },
};

function spawnRect(id: AppId, index: number): Rect {
  const { w, h } = SIZES[id];
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = Math.min(w, vw - 40);
  const height = Math.min(h, vh - 140);
  return {
    x: Math.max(16, (vw - width) / 2 + ((index % 5) - 2) * 34),
    y: Math.max(46, (vh - height - 70) / 2 + (index % 4) * 26),
    w: width,
    h: height,
  };
}

export type Theme = "dark" | "light";

interface OSStore {
  phase: "landing" | "boot" | "login" | "desktop";
  setPhase: (p: OSStore["phase"]) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;

  user: SessionUser | null;
  token: string | null;
  live: boolean;
  setLive: (b: boolean) => void;
  login: (u: SessionUser, token: string | null) => void;
  logout: () => void;

  windows: Win[];
  topZ: number;
  spawned: number;
  open: (id: AppId) => void;
  close: (id: AppId) => void;
  focus: (id: AppId) => void;
  minimize: (id: AppId) => void;
  toggleMax: (id: AppId) => void;
  setRect: (id: AppId, rect: Rect) => void;

  paletteOpen: boolean;
  setPalette: (b: boolean) => void;
  agentBusy: boolean;
  setAgentBusy: (b: boolean) => void;
  chatDraft: string;
  knowledgeQuery: string;
  setKnowledgeQuery: (q: string) => void;
  setChatDraft: (s: string) => void;

  /* realtime (live mode) */
  wsConnected: boolean;
  setWsConnected: (b: boolean) => void;
  online: PresenceUser[];
  setOnline: (u: PresenceUser[]) => void;
  liveFeed: FeedEvent[];
  pushFeed: (e: Omit<FeedEvent, "id" | "time">) => void;

  /* incoming video call (WebRTC ring) */
  ring: { id: string; name: string; hue: number; roster?: { id: string; name: string; hue: number }[] } | null;
  setRing: (r: OSStore["ring"]) => void;
}

const savedTheme = ((): Theme => {
  try {
    return localStorage.getItem("eaios-theme") === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
})();
document.documentElement.dataset.theme = savedTheme;

export const useOS = create<OSStore>((set, get) => ({
  phase: "landing",
  setPhase: (phase) => set({ phase }),
  theme: savedTheme,
  setTheme: (theme) => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("eaios-theme", theme);
    } catch {
      /* private mode */
    }
    set({ theme });
  },

  user: null,
  token: null,
  live: false,
  setLive: (live) => set({ live }),
  login: (user, token) => set({ user, token, phase: "desktop" }),
  logout: () => set({ user: null, token: null, windows: [], phase: "login" }),

  windows: [],
  topZ: 100,
  spawned: 0,
  open: (id) => {
    const { windows, topZ, spawned } = get();
    const existing = windows.find((w) => w.id === id);
    if (existing) {
      set({
        topZ: topZ + 1,
        windows: windows.map((w) => (w.id === id ? { ...w, minimized: false, z: topZ + 1 } : w)),
      });
      return;
    }
    set({
      topZ: topZ + 1,
      spawned: spawned + 1,
      windows: [...windows, { id, rect: spawnRect(id, spawned), z: topZ + 1, minimized: false, maximized: false }],
    });
  },
  close: (id) => set((s) => ({ windows: s.windows.filter((w) => w.id !== id) })),
  focus: (id) =>
    set((s) => ({
      topZ: s.topZ + 1,
      windows: s.windows.map((w) => (w.id === id ? { ...w, z: s.topZ + 1 } : w)),
    })),
  minimize: (id) => set((s) => ({ windows: s.windows.map((w) => (w.id === id ? { ...w, minimized: true } : w)) })),
  toggleMax: (id) =>
    set((s) => ({
      topZ: s.topZ + 1,
      windows: s.windows.map((w) => {
        if (w.id !== id) return w;
        if (w.maximized) return { ...w, maximized: false, rect: w.prevRect ?? w.rect, z: s.topZ + 1 };
        return {
          ...w,
          maximized: true,
          prevRect: w.rect,
          z: s.topZ + 1,
          rect: { x: 0, y: 34, w: window.innerWidth, h: window.innerHeight - 34 },
        };
      }),
    })),
  setRect: (id, rect) => set((s) => ({ windows: s.windows.map((w) => (w.id === id ? { ...w, rect } : w)) })),

  paletteOpen: false,
  setPalette: (paletteOpen) => set({ paletteOpen }),
  agentBusy: false,
  setAgentBusy: (agentBusy) => set({ agentBusy }),
  chatDraft: "",
  setChatDraft: (chatDraft) => set({ chatDraft }),
  knowledgeQuery: "",
  setKnowledgeQuery: (knowledgeQuery) => set({ knowledgeQuery }),

  wsConnected: false,
  setWsConnected: (wsConnected) => set({ wsConnected }),
  online: [],
  setOnline: (online) => set({ online }),
  liveFeed: [],
  pushFeed: (e) =>
    set((s) => ({
      liveFeed: [
        {
          ...e,
          id: Date.now() + Math.random(),
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
        },
        ...s.liveFeed,
      ].slice(0, 40),
    })),

  ring: null,
  setRing: (ring) => set({ ring }),
}));
