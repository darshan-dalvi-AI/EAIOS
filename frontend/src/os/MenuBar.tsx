import { LogOut, Moon, Search, Sun, Wifi, WifiOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useOS } from "../store";

export default function MenuBar() {
  const { user, live, agentBusy, setPalette, logout, open, online, wsConnected, theme, setTheme } = useOS();
  const [now, setNow] = useState(new Date());
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    window.addEventListener("pointerdown", onClick);
    return () => window.removeEventListener("pointerdown", onClick);
  }, []);

  return (
    <nav className="menubar">
      <button className="mb-logo" onClick={() => open("settings")} aria-label="EAIOS system menu">
        <span className={`orb ${agentBusy ? "busy" : ""}`} />
        EAIOS
      </button>
      {["File", "View", "Agents", "Help"].map((m) => (
        <button key={m} className="mb-item" onClick={() => setPalette(true)}>{m}</button>
      ))}

      <div className="mb-right">
        {wsConnected && online.length > 0 && (
          <div className="mb-status" title={`Online now: ${online.map((u) => u.name).join(", ")}`}>
            <span style={{ display: "flex", marginRight: 2 }}>
              {online.slice(0, 4).map((u, i) => (
                <span
                  key={u.id}
                  className="avatar sm"
                  style={{
                    "--hue": u.hue, width: 16, height: 16, fontSize: 8,
                    marginLeft: i === 0 ? 0 : -5, border: "1px solid var(--bg, #000)",
                  } as React.CSSProperties}
                >
                  {u.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
                </span>
              ))}
            </span>
            {online.length} online
          </div>
        )}
        <div className="mb-status" title={live ? "FastAPI backend connected" : "Running on mock data"}>
          <span className={`dot ${live ? "pulse" : "off"}`} />
          {live ? "Live" : "Demo"}
        </div>
        <div className="mb-status" title="Agent activity">
          <span className={`dot ${agentBusy ? "pulse" : ""}`} style={{ background: agentBusy ? "var(--accent)" : "var(--text-faint)" }} />
          {agentBusy ? "Agents working" : "Agents idle"}
        </div>
        <button className="mb-item" onClick={() => setPalette(true)} aria-label="Open command palette (Ctrl+K)">
          <Search size={14} />
        </button>
        <button
          className="mb-item"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          title={`${theme === "dark" ? "Light" : "Dark"} mode`}
        >
          {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
        </button>
        <span className="mb-item" aria-hidden>{live ? <Wifi size={14} /> : <WifiOff size={14} />}</span>
        <span className="mb-clock">
          {now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}{"  "}
          {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>

        <div ref={menuRef} style={{ position: "relative" }}>
          <button onClick={() => setMenuOpen((v) => !v)} aria-label="User menu" style={{ display: "flex" }}>
            <div className="avatar sm" style={{ "--hue": user?.avatar_hue ?? 210 } as React.CSSProperties}>
              {user?.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
            </div>
          </button>
          {menuOpen && (
            <div
              className="card"
              style={{ position: "absolute", right: 0, top: 34, width: 210, zIndex: 500, background: "var(--surface-solid)", display: "flex", flexDirection: "column", gap: 8 }}
            >
              <div>
                <div style={{ fontWeight: 600 }}>{user?.full_name}</div>
                <div className="faint" style={{ fontSize: 11 }}>{user?.email}</div>
                <span className="pill info" style={{ marginTop: 6 }}>{user?.role}</span>
              </div>
              <button className="btn sm" onClick={logout} style={{ justifyContent: "center" }}>
                <LogOut size={13} /> Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
