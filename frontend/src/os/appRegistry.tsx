import {
  Activity,
  BarChart3,
  Bot,
  Cloud,
  Database,
  FolderSearch,
  LayoutDashboard,
  MessageSquare,
  Mic,
  Settings,
  Share2,
  ShieldCheck,
  TerminalSquare,
  Video,
  Wand2,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { AppId } from "../types";

export const APP_META: Record<AppId, { name: string; hue: number; Icon: LucideIcon; tagline: string }> = {
  chat:        { name: "AI Chat",     hue: 200, Icon: MessageSquare,  tagline: "Multi-agent enterprise assistant" },
  knowledge:   { name: "Knowledge",   hue: 155, Icon: FolderSearch,   tagline: "Documents & RAG pipeline" },
  agents:      { name: "Agents",      hue: 265, Icon: Bot,            tagline: "Agent fleet & live activity" },
  graph:       { name: "Graph",       hue: 175, Icon: Share2,         tagline: "Knowledge graph explorer" },
  automations: { name: "Automations", hue: 95,  Icon: Workflow,       tagline: "Visual workflow builder" },
  traces:      { name: "Traces",      hue: 320, Icon: Activity,       tagline: "Observability & span waterfalls" },
  sql:         { name: "SQL Studio",  hue: 130, Icon: Database,       tagline: "Natural language database assistant" },
  analytics:   { name: "Analytics",   hue: 38,  Icon: BarChart3,      tagline: "Usage metrics & insights" },
  dashboards:  { name: "Dashboards",  hue: 260, Icon: LayoutDashboard, tagline: "Natural-language BI charts" },
  studio:      { name: "Agent Studio", hue: 285, Icon: Wand2,         tagline: "Build custom AI agents, no code" },
  connectors:  { name: "Connectors",  hue: 175, Icon: Cloud,          tagline: "Gmail, Drive & more → knowledge" },
  meeting:     { name: "Meeting",     hue: 15,  Icon: Mic,            tagline: "Record → transcript → minutes" },
  video:       { name: "Video Call",  hue: 340, Icon: Video,          tagline: "AI video calls — captions, MoM, effects" },
  admin:       { name: "Admin",       hue: 350, Icon: ShieldCheck,    tagline: "Users, audit, models" },
  terminal:    { name: "Terminal",    hue: 220, Icon: TerminalSquare, tagline: "EAIOS shell" },
  settings:    { name: "Settings",    hue: 285, Icon: Settings,       tagline: "System preferences" },
};

export const APP_ORDER: AppId[] = [
  "chat", "knowledge", "connectors", "agents", "studio", "graph", "automations", "traces",
  "sql", "analytics", "dashboards", "meeting", "video", "admin", "terminal", "settings",
];

export function AppTile({ id, size = "" }: { id: AppId; size?: "" | "sm" | "md" }) {
  const { hue, Icon, name } = APP_META[id];
  const iconSize = size === "sm" ? 12 : size === "md" ? 17 : 24;
  return (
    <div className={`app-icon ${size}`} style={{ "--hue": hue } as React.CSSProperties} role="img" aria-label={name}>
      <Icon size={iconSize} strokeWidth={2.2} />
    </div>
  );
}
