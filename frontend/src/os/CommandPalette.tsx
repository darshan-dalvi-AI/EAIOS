import { Bot, LogOut, Search, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useOS } from "../store";
import type { AppId } from "../types";
import { APP_META, APP_ORDER, AppTile } from "./appRegistry";

interface Item {
  key: string;
  section: "Apps" | "Actions";
  label: string;
  hint?: string;
  icon: React.ReactNode;
  run: () => void;
}

export default function CommandPalette() {
  const { setPalette, open, logout, setChatDraft } = useOS();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => inputRef.current?.focus(), []);

  const items = useMemo<Item[]>(() => {
    const apps: Item[] = APP_ORDER.map((id: AppId) => ({
      key: `app-${id}`,
      section: "Apps",
      label: APP_META[id].name,
      hint: APP_META[id].tagline,
      icon: <AppTile id={id} size="md" />,
      run: () => open(id),
    }));
    const actions: Item[] = [
      {
        key: "ask",
        section: "Actions",
        label: query.trim() ? `Ask AI: “${query.trim()}”` : "Ask the AI anything…",
        hint: "Routes through the agent orchestrator",
        icon: <Sparkles size={17} style={{ color: "var(--accent)" }} />,
        run: () => {
          if (query.trim()) setChatDraft(query.trim());
          open("chat");
        },
      },
      {
        key: "agents",
        section: "Actions",
        label: "Show agent activity",
        icon: <Bot size={17} style={{ color: "#c4b5fd" }} />,
        run: () => open("agents"),
      },
      {
        key: "logout",
        section: "Actions",
        label: "Log out",
        icon: <LogOut size={17} className="muted" />,
        run: logout,
      },
    ];
    const all = [...apps, ...actions];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    const matched = all.filter((i) => i.label.toLowerCase().includes(q) || i.hint?.toLowerCase().includes(q));
    const ask = all.find((i) => i.key === "ask")!;
    return matched.length ? (matched.some((m) => m.key === "ask") ? matched : [...matched, ask]) : [ask];
  }, [query, open, logout, setChatDraft]);

  useEffect(() => setIndex(0), [query]);

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => (i + 1) % items.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => (i - 1 + items.length) % items.length); }
    else if (e.key === "Enter") { items[index]?.run(); setPalette(false); }
    else if (e.key === "Escape") setPalette(false);
  }

  let lastSection = "";
  return (
    <div className="palette-veil" onPointerDown={(e) => e.target === e.currentTarget && setPalette(false)}>
      <div className="palette" role="dialog" aria-label="Command palette">
        <div className="palette-input">
          <Search size={17} className="faint" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search apps, run commands, or ask the AI…"
            aria-label="Command input"
          />
          <span className="kbd">esc</span>
        </div>
        <div className="palette-list">
          {items.map((item, i) => {
            const header = item.section !== lastSection ? <div className="palette-section">{item.section}</div> : null;
            lastSection = item.section;
            return (
              <div key={item.key}>
                {header}
                <button
                  className={`palette-item ${i === index ? "active" : ""}`}
                  onPointerEnter={() => setIndex(i)}
                  onClick={() => { item.run(); setPalette(false); }}
                >
                  {item.icon}
                  <span>
                    <div style={{ fontSize: 13.5 }}>{item.label}</div>
                    {item.hint && <div className="faint" style={{ fontSize: 11 }}>{item.hint}</div>}
                  </span>
                  {i === index && <span className="kbd">↵</span>}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
