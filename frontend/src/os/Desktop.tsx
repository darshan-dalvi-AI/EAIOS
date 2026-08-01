import {
  lazy, Suspense, useEffect, useState,
  type ComponentType, type LazyExoticComponent,
} from "react";
// Each app is a separate chunk, fetched the first time its window opens rather
// than baked into the initial bundle. The OS shell no longer ships all 18 apps
// up front (~860 KB of JS); it ships the desktop, and the app you open.
const AdminApp = lazy(() => import("../apps/AdminApp"));
const AgentsApp = lazy(() => import("../apps/AgentsApp"));
const AnalyticsApp = lazy(() => import("../apps/AnalyticsApp"));
const AutomationsApp = lazy(() => import("../apps/AutomationsApp"));
const ChatApp = lazy(() => import("../apps/ChatApp"));
const CodeApp = lazy(() => import("../apps/CodeApp"));
const ConnectorsApp = lazy(() => import("../apps/ConnectorsApp"));
const DashboardsApp = lazy(() => import("../apps/DashboardsApp"));
const GraphApp = lazy(() => import("../apps/GraphApp"));
const KnowledgeApp = lazy(() => import("../apps/KnowledgeApp"));
const MeetingApp = lazy(() => import("../apps/MeetingApp"));
const SearchApp = lazy(() => import("../apps/SearchApp"));
const SettingsApp = lazy(() => import("../apps/SettingsApp"));
const StudioApp = lazy(() => import("../apps/StudioApp"));
const SQLApp = lazy(() => import("../apps/SQLApp"));
const TasksApp = lazy(() => import("../apps/TasksApp"));
const TerminalApp = lazy(() => import("../apps/TerminalApp"));
const TracesApp = lazy(() => import("../apps/TracesApp"));
const VideoApp = lazy(() => import("../apps/VideoApp"));
import { connectRealtime, disconnectRealtime } from "../lib/ws";
import { useOS } from "../store";
import type { AppId } from "../types";
import CommandPalette from "./CommandPalette";
import Dock from "./Dock";
import IndustryWizard from "./IndustryWizard";
import MobileTabBar from "./MobileTabBar";
import MenuBar from "./MenuBar";
import SetupGuide from "./SetupGuide";
import DemoBanner from "./DemoBanner";
import Toasts from "./Toasts";
import UpgradeDialog from "./UpgradeDialog";
import Tour from "./Tour";
import WakeWord from "./WakeWord";
import Window from "./Window";

const COMPONENTS: Record<AppId, LazyExoticComponent<ComponentType>> = {
  chat: ChatApp,
  knowledge: KnowledgeApp,
  agents: AgentsApp,
  graph: GraphApp,
  automations: AutomationsApp,
  traces: TracesApp,
  search: SearchApp,
  tasks: TasksApp,
  sql: SQLApp,
  analytics: AnalyticsApp,
  dashboards: DashboardsApp,
  studio: StudioApp,
  connectors: ConnectorsApp,
  meeting: MeetingApp,
  video: VideoApp,
  code: CodeApp,
  admin: AdminApp,
  terminal: TerminalApp,
  settings: SettingsApp,
};

export default function Desktop() {
  const { windows, paletteOpen, setPalette, open, reclampWindows } = useOS();
  const [tour, setTour] = useState(() => localStorage.getItem("eaios-tour-done") !== "1");
  const [wake, setWake] = useState(() => localStorage.getItem("eaios-wake") === "1");

  // Settings can replay the tour / toggle the wake word via these events
  useEffect(() => {
    const onTour = () => setTour(true);
    const onWake = () => setWake(localStorage.getItem("eaios-wake") === "1");
    window.addEventListener("k-os:replay-tour", onTour);
    window.addEventListener("k-os:wake-changed", onWake);
    return () => { window.removeEventListener("k-os:replay-tour", onTour); window.removeEventListener("k-os:wake-changed", onWake); };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(!useOS.getState().paletteOpen);
      }
      if (e.key === "Escape") setPalette(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPalette]);

  // Realtime: presence + live agent feed (live mode only; no-op in demo)
  useEffect(() => {
    connectRealtime();
    return () => disconnectRealtime();
  }, []);

  // Keep windows inside the viewport after a resize or a phone rotation —
  // otherwise a window can end up wider than, or off, the screen with no way
  // to drag it back. Debounced so a drag-resize doesn't thrash the layout.
  useEffect(() => {
    let t: number | undefined;
    const onResize = () => {
      window.clearTimeout(t);
      t = window.setTimeout(reclampWindows, 150);
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("orientationchange", onResize);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("orientationchange", onResize);
    };
  }, [reclampWindows]);

  // First-run: open the chat app front and center
  useEffect(() => {
    if (useOS.getState().windows.length === 0) open("chat");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allMinimized = windows.every((w) => w.minimized);

  return (
    <>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <MenuBar />
      {(windows.length === 0 || allMinimized) && (
        <div className="empty" style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
          <div className="boot-logo" style={{ fontSize: 26, opacity: 0.7 }}>K-OS</div>
          <div className="hide-on-phone">
            Press <span className="kbd">Ctrl</span> + <span className="kbd">K</span> or pick an app from the taskbar
          </div>
          <div className="show-on-phone">Tap an app below to get started</div>
        </div>
      )}
      <main id="main-content" style={{ position: "fixed", inset: 0, zIndex: "var(--z-window)" as unknown as number }}>
        {windows.map((win) => {
          const Component = COMPONENTS[win.id];
          // Unknown app id (stale session state from an older/newer bundle):
          // skip it instead of crashing the whole desktop.
          if (!Component) return null;
          return (
            <Window key={win.id} win={win}>
              <Suspense fallback={<div className="app-loading" style={{ padding: 24, opacity: 0.6 }}>Loading…</div>}>
                <Component />
              </Suspense>
            </Window>
          );
        })}
      </main>
      <Dock />
      <MobileTabBar />
      <DemoBanner />
      <Toasts />
      {/* Raised by api.ts on any 402, so a plan limit is offered as an
          upgrade wherever it happens rather than surfacing as an error. */}
      <UpgradeDialog />
      {paletteOpen && <CommandPalette />}
      {wake && <WakeWord />}
      {tour && <Tour onDone={() => { localStorage.setItem("eaios-tour-done", "1"); setTour(false); }} />}
      {!tour && <IndustryWizard />}
      {!tour && <SetupGuide />}
    </>
  );
}
