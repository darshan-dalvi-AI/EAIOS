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
  code: { w: 1020, h: 660 },
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
  orgName: string | null;
  /** True when this account is a platform owner (PLATFORM_OWNER_EMAILS on the
   *  server) — unlocks the Workspaces console for managing every tenant. */
  isOwner: boolean;
  /** Industry profile applied to this workspace ("" = never asked). */
  industry: string;
  setIndustry: (i: string) => void;
  /** False while a password signup still has to enter its emailed code. */
  emailVerified: boolean;
  /** This workspace is a throwaway sandbox: real to use, deleted afterwards. */
  demo: boolean;
  demoExpiresIn: number | null;
  live: boolean;
  setLive: (b: boolean) => void;
  login: (u: SessionUser, token: string | null, orgName?: string | null, isOwner?: boolean, industry?: string, emailVerified?: boolean, demo?: boolean, demoExpiresIn?: number | null) => void;
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
  reclampWindows: () => void;

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
  orgName: null,
  isOwner: false,
  industry: "",
  setIndustry: (industry) => set({ industry }),
  emailVerified: true,
  demo: false,
  demoExpiresIn: null,
  live: false,
  setLive: (live) => set({ live }),
  login: (user, token, orgName = null, isOwner = false, industry = "", emailVerified = true,
         demo = false, demoExpiresIn = null) =>
    set({ user, token, orgName, isOwner, industry, emailVerified, demo, demoExpiresIn, phase: "desktop" }),
  logout: () => set({ user: null, token: null, orgName: null, isOwner: false, industry: "", emailVerified: true, demo: false, demoExpiresIn: null, windows: [], phase: "login" }),

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

  // After a viewport change (resize, phone rotation) an open window can be left
  // wider than the screen or pushed off the edge, with no way to drag it back.
  // Re-clamp every window into the new bounds; a maximized one just re-fills.
  reclampWindows: () => set((s) => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const minW = Math.min(420, vw - 24);
    const minH = Math.min(280, vh - 80);
    return {
      windows: s.windows.map((w) => {
        if (w.maximized) return { ...w, rect: { x: 0, y: 34, w: vw, h: vh - 34 } };
        const width = Math.min(w.rect.w, vw - 24);
        const height = Math.min(w.rect.h, vh - 80);
        return {
          ...w,
          rect: {
            w: Math.max(minW, width),
            h: Math.max(minH, height),
            x: Math.min(Math.max(12, w.rect.x), Math.max(12, vw - width - 12)),
            y: Math.min(Math.max(34, w.rect.y), Math.max(34, vh - height - 12)),
          },
        };
      }),
    };
  }),

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
