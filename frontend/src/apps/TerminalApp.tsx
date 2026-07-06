import { useEffect, useRef, useState } from "react";
import { AGENTS, DOCS } from "../lib/mock";
import { useOS } from "../store";
import type { AppId } from "../types";

interface Line {
  html: string;
}

const BANNER = [
  "EAIOS shell 0.1.0 — type <span class='cy'>help</span> for commands",
];

export default function TerminalApp() {
  const { user, open } = useOS();
  const [lines, setLines] = useState<Line[]>(BANNER.map((html) => ({ html })));
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [histIndex, setHistIndex] = useState(-1);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => endRef.current?.scrollIntoView(), [lines]);

  function print(...html: string[]) {
    setLines((l) => [...l, ...html.map((h) => ({ html: h }))]);
  }

  function execute(raw: string) {
    const cmd = raw.trim();
    print(`<span class='p'>${user?.email.split("@")[0]}@eaios</span><span class='dim'>:~$</span> ${escapeHtml(cmd)}`);
    if (!cmd) return;
    setHistory((h) => [cmd, ...h]);
    setHistIndex(-1);

    const [name, ...args] = cmd.split(/\s+/);
    switch (name.toLowerCase()) {
      case "help":
        print(
          "<span class='cy'>help</span>        this list",
          "<span class='cy'>neofetch</span>    system summary",
          "<span class='cy'>agents</span>      registered agent fleet",
          "<span class='cy'>docs</span>        knowledge base contents",
          "<span class='cy'>stats</span>       platform counters",
          "<span class='cy'>open</span> &lt;app&gt;  launch an app (chat, knowledge, agents, sql, analytics, admin, settings)",
          "<span class='cy'>whoami</span>      current session",
          "<span class='cy'>clear</span>       clear screen"
        );
        break;
      case "neofetch":
        print(
          "<span class='vi'>        ▄▄▄▄▄▄▄        </span> <span class='cy'>EAIOS</span> 0.1.0 <span class='dim'>“Aurora”</span>",
          "<span class='vi'>      ▄█▀▀▀▀▀▀▀█▄      </span> Kernel: hybrid-rag/1.4",
          "<span class='vi'>     ██  ◉   ◉  ██     </span> Agents: 8 registered · planner warm",
          "<span class='vi'>     ██    ▽    ██     </span> Vectors: qdrant <span class='dim'>(in-memory fallback)</span>",
          "<span class='vi'>      ▀█▄▄▄▄▄▄▄█▀      </span> LLM: mock <span class='dim'>· ollama-ready</span>",
          `<span class='vi'>        ▀▀▀▀▀▀▀        </span> Session: ${user?.role} · ${user?.email}`
        );
        break;
      case "agents":
        AGENTS.forEach((a) =>
          print(`<span class='cy'>${a.id.padEnd(10)}</span> ${a.status === "active" ? "<span class='p'>●</span>" : "<span class='dim'>○</span>"} ${a.name.padEnd(18)} <span class='dim'>${a.runs} runs · ${a.avg_ms}ms avg</span>`)
        );
        break;
      case "docs":
        DOCS.slice(0, 8).forEach((d) =>
          print(`<span class='dim'>${d.doc_type.padEnd(6)}</span> ${escapeHtml(d.title).padEnd(34)} <span class='${d.status === "indexed" ? "p" : "dim"}'>${d.status}</span> <span class='dim'>${d.chunk_count} chunks</span>`)
        );
        break;
      case "stats":
        print(
          `documents: <span class='cy'>${DOCS.length}</span> · chunks: <span class='cy'>${DOCS.reduce((s, d) => s + d.chunk_count, 0)}</span> · agents: <span class='cy'>${AGENTS.length}</span> · runs: <span class='cy'>${AGENTS.reduce((s, a) => s + a.runs, 0).toLocaleString()}</span>`
        );
        break;
      case "whoami":
        print(`${user?.full_name} <span class='dim'>&lt;${user?.email}&gt;</span> · role=<span class='cy'>${user?.role}</span> · jwt=<span class='p'>valid</span>`);
        break;
      case "open": {
        const app = (args[0] || "") as AppId;
        const valid: AppId[] = ["chat", "knowledge", "agents", "sql", "analytics", "admin", "terminal", "settings"];
        if (valid.includes(app)) {
          open(app);
          print(`<span class='p'>launched</span> ${app}`);
        } else print(`<span class='dim'>unknown app “${escapeHtml(args[0] ?? "")}” — try: ${valid.join(", ")}</span>`);
        break;
      }
      case "echo":
        print(escapeHtml(args.join(" ")));
        break;
      case "clear":
        setLines([]);
        break;
      default:
        print(`<span class='dim'>command not found: ${escapeHtml(name)} — try</span> <span class='cy'>help</span>`);
    }
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      execute(input);
      setInput("");
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = Math.min(histIndex + 1, history.length - 1);
      if (history[next]) { setHistIndex(next); setInput(history[next]); }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = histIndex - 1;
      setHistIndex(next);
      setInput(next >= 0 ? history[next] : "");
    }
  }

  return (
    <div className="term" onClick={() => inputRef.current?.focus()}>
      {lines.map((line, i) => (
        <div key={i} dangerouslySetInnerHTML={{ __html: line.html }} />
      ))}
      <div className="cmd-line">
        <span className="p">{user?.email.split("@")[0]}@eaios</span>
        <span className="dim">:~$</span>
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          aria-label="Terminal input"
          autoFocus
          spellCheck={false}
        />
      </div>
      <div ref={endRef} />
    </div>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
