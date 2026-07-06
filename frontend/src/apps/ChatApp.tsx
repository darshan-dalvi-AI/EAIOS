import { Bot, Check, Copy, Download, FileText, Mic, Plus, RefreshCw, Send, Sparkles, Square, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiChatStream } from "../lib/api";
import { AGENTS } from "../lib/mock";
import { useOS } from "../store";
import type { ChatMsg } from "../types";

let msgId = 0;
const nid = () => `msg-${++msgId}`;

const SUGGESTIONS = [
  "How many annual leave days do we get?",
  "Summarize Q3 revenue performance",
  "How do I restore an Atlas backup?",
  "Write a Python function to restore a backup",
  "Draft an email about the deployment timeline",
];

export default function ChatApp() {
  const { user, setAgentBusy, chatDraft, setChatDraft } = useOS();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [agent, setAgent] = useState("auto");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [listening, setListening] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const lastUserText = useRef("");

  function startVoice() {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = "en-IN";
    rec.interimResults = true;
    rec.onresult = (e: any) => setInput(Array.from(e.results).map((r: any) => r[0].transcript).join(""));
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    setListening(true);
    rec.start();
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  // Command-palette "Ask AI" hand-off (ref-guarded: StrictMode double-invoke safe)
  const lastDraft = useRef("");
  useEffect(() => {
    if (!chatDraft) {
      lastDraft.current = "";
      return;
    }
    if (chatDraft !== lastDraft.current) {
      lastDraft.current = chatDraft;
      setChatDraft("");
      void send(chatDraft);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatDraft]);

  const patchMsg = (id: string, patch: Partial<ChatMsg> | ((m: ChatMsg) => Partial<ChatMsg>)) =>
    setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)));

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy) return;
    lastUserText.current = clean;
    setInput("");
    setBusy(true);
    setAgentBusy(true);
    setMessages((m) => [...m, { id: nid(), role: "user", content: clean }]);

    const aiId = nid();
    setMessages((m) => [...m, { id: aiId, role: "assistant", content: "", streaming: true }]);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await apiChatStream(
        clean,
        agent === "auto" ? undefined : agent,
        {
          onMeta: (meta) => patchMsg(aiId, { agent: meta.agent, plan: meta.plan, citations: meta.citations, confidence: meta.confidence }),
          onDelta: (t) => patchMsg(aiId, (m) => ({ content: m.content + t })),
        },
        controller.signal,
      );
      patchMsg(aiId, { streaming: false });
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        patchMsg(aiId, (m) => ({ streaming: false, content: m.content || "*(stopped)*" }));
      } else {
        patchMsg(aiId, { streaming: false, content: `Something went wrong: ${err}`, agent: "system", confidence: 0 });
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
      setAgentBusy(false);
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function regenerate() {
    if (busy || !lastUserText.current) return;
    setMessages((all) => {
      const copy = [...all];
      if (copy.at(-1)?.role === "assistant") copy.pop();
      if (copy.at(-1)?.role === "user") copy.pop();
      return copy;
    });
    void send(lastUserText.current);
  }

  function exportChat() {
    const lines = messages.map((m) => {
      if (m.role === "user") return `**${user?.full_name ?? "You"}:** ${m.content}`;
      const meta = [m.agent && `agent: ${m.agent}`, m.confidence ? `confidence: ${m.confidence}%` : ""].filter(Boolean).join(" · ");
      const cites = (m.citations ?? []).map((c, i) => `[${i + 1}] ${c.title}${c.section ? ` — ${c.section}` : ""}`).join("\n");
      return `**EAIOS${m.agent ? ` (${m.agent})` : ""}:** ${m.content}${meta ? `\n\n_${meta}_` : ""}${cites ? `\n\nSources:\n${cites}` : ""}`;
    });
    const blob = new Blob([`# EAIOS conversation — ${new Date().toLocaleString()}\n\n${lines.join("\n\n---\n\n")}\n`], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `eaios-chat-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const lastDone = !busy && messages.at(-1)?.role === "assistant";

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <Sparkles size={15} style={{ color: "var(--accent)" }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>Enterprise Assistant</span>
        <span className="pill dim">multi-agent</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <label className="faint" style={{ fontSize: 11 }} htmlFor="agent-select">Route</label>
          <select id="agent-select" className="plain" value={agent} onChange={(e) => setAgent(e.target.value)}>
            <option value="auto">Auto (planner)</option>
            {AGENTS.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          {messages.length > 0 && (
            <button className="btn sm" onClick={exportChat} aria-label="Export conversation as Markdown" title="Export .md">
              <Download size={13} />
            </button>
          )}
          <button className="btn sm" onClick={() => setMessages([])} aria-label="New conversation">
            <Plus size={13} /> New
          </button>
        </div>
      </div>

      <div className="app-content" ref={scrollRef} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {messages.length === 0 && !busy && (
          <div className="empty">
            <div className="orb" style={{ width: 34, height: 34 }} />
            <h2 className="h-display" style={{ fontSize: 19 }}>
              Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}, {user?.full_name.split(" ")[0]}
            </h2>
            <p className="muted" style={{ maxWidth: 400, margin: 0 }}>
              Ask anything about your enterprise knowledge. The planner routes each request to the right agent automatically.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 520 }}>
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn sm" onClick={() => void send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <Bubble key={m.id} msg={m} isLast={i === messages.length - 1} onRegenerate={regenerate} canRegenerate={lastDone} />
        ))}

        {busy && messages.at(-1)?.content === "" && (
          <div className="msg ai">
            <div className="avatar sm" style={{ "--hue": 265 } as React.CSSProperties}><Bot size={13} /></div>
            <div className="bubble">
              <span className="plan-chip"><span className="dot pulse" style={{ background: "var(--accent)" }} /> Planning Agent — routing request…</span>
            </div>
          </div>
        )}
      </div>

      <form
        className="app-toolbar"
        style={{ borderTop: "1px solid var(--hairline)", borderBottom: "none" }}
        onSubmit={(e) => { e.preventDefault(); void send(input); }}
      >
        <div className="field" style={{ flex: 1 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about policies, financials, product docs — or say “remember that…”"
            aria-label="Message"
          />
        </div>
        <button
          type="button"
          className="btn"
          onClick={startVoice}
          aria-label="Voice input"
          title="Speak your question (Web Speech API)"
          style={listening ? { borderColor: "var(--accent)", color: "var(--accent)", boxShadow: "var(--glow)" } : {}}
        >
          <Mic size={14} />
        </button>
        {busy ? (
          <button type="button" className="btn" onClick={stop} aria-label="Stop generation" title="Stop generation">
            <Square size={13} /> Stop
          </button>
        ) : (
          <button className="btn primary" disabled={!input.trim()} aria-label="Send message">
            <Send size={14} /> Send
          </button>
        )}
      </form>
    </div>
  );
}

/* ── message rendering ─────────────────────────────────────────────────── */

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="codeblock">
      <div className="codeblock-bar">
        <span>{lang || "code"}</span>
        <button
          onClick={() => {
            navigator.clipboard?.writeText(code).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1400);
            });
          }}
          aria-label="Copy code"
        >
          {copied ? <Check size={11} /> : <Copy size={11} />} {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  );
}

function Inline({ text }: { text: string }) {
  // minimal inline markdown: `code` and **bold**
  const parts = text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="inline-code">{p.slice(1, -1)}</code>;
        if (p.startsWith("**") && p.endsWith("**")) return <b key={i}>{p.slice(2, -2)}</b>;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

function RichText({ content }: { content: string }) {
  // split into text / fenced-code segments
  const segments = content.split(/(```[\s\S]*?(?:```|$))/g);
  return (
    <>
      {segments.map((seg, i) => {
        if (seg.startsWith("```")) {
          const body = seg.replace(/^```/, "").replace(/```$/, "");
          const nl = body.indexOf("\n");
          const lang = nl > -1 ? body.slice(0, nl).trim() : "";
          const code = nl > -1 ? body.slice(nl + 1) : body;
          return <CodeBlock key={i} code={code.replace(/\n$/, "")} lang={lang} />;
        }
        return seg ? <span key={i}><Inline text={seg} /></span> : null;
      })}
    </>
  );
}

function Bubble({ msg, isLast, canRegenerate, onRegenerate }: {
  msg: ChatMsg;
  isLast: boolean;
  canRegenerate: boolean;
  onRegenerate: () => void;
}) {
  const agentMeta = AGENTS.find((a) => a.id === msg.agent);
  const done = !msg.streaming;

  if (msg.role === "user") {
    return (
      <div className="msg user">
        <div className="bubble">{msg.content}</div>
      </div>
    );
  }

  return (
    <div className="msg ai" style={{ flexDirection: "column", gap: 7, alignItems: "flex-start" }}>
      {msg.plan && msg.plan.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {msg.plan.map((p, i) => (
            <span key={i} className="plan-chip done">
              <Bot size={11} /> {p}
            </span>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 11, maxWidth: "100%" }}>
        <div className="avatar sm" style={{ "--hue": agentMeta?.hue ?? 200, flexShrink: 0 } as React.CSSProperties}><Bot size={13} /></div>
        <div className="bubble" style={{ whiteSpace: "pre-wrap", minWidth: 0 }}>
          <span className={done ? "" : "caret"}><RichText content={msg.content} /></span>
        </div>
      </div>
      {done && (msg.citations?.length || msg.confidence !== undefined) && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", paddingLeft: 37 }}>
          {msg.citations?.map((c, i) => (
            <button key={i} className="cite" title={`relevance ${(c.score * 100).toFixed(0)}%`}>
              <FileText size={11} />
              {c.title}{c.section ? ` · ${c.section}` : ""}
              <span className="meter" style={{ width: 30 }}><i style={{ width: `${c.score * 100}%` }} /></span>
            </button>
          ))}
          <button
            className="cite"
            onClick={() => {
              speechSynthesis.cancel();
              speechSynthesis.speak(new SpeechSynthesisUtterance(msg.content.replace(/```[\s\S]*?```/g, "code block omitted.")));
            }}
            aria-label="Read answer aloud"
          >
            <Volume2 size={11} /> listen
          </button>
          {isLast && canRegenerate && (
            <button className="cite" onClick={onRegenerate} aria-label="Regenerate response">
              <RefreshCw size={11} /> regenerate
            </button>
          )}
          {msg.confidence !== undefined && msg.confidence > 0 && (
            <span className={`pill ${msg.confidence >= 75 ? "good" : msg.confidence >= 50 ? "warn" : "bad"}`}>
              confidence {msg.confidence}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
