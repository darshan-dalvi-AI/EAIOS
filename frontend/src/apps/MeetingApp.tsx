/* AI Meeting Assistant — record (Web Speech) or paste a transcript,
   generate structured minutes (summary · decisions · action items),
   optionally save transcript + minutes into the knowledge base. */
import { BookOpenCheck, CircleStop, FileText, Loader2, Mic, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiMeeting } from "../lib/api";
import { useOS } from "../store";

type SpeechRec = {
  start: () => void; stop: () => void;
  continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: (() => void) | null;
};

function getRecognizer(): SpeechRec | null {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

export default function MeetingApp() {
  const live = useOS((s) => s.live);
  const [title, setTitle] = useState("Team meeting");
  const [transcript, setTranscript] = useState("");
  const [interim, setInterim] = useState("");
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [save, setSave] = useState(true);
  const [minutes, setMinutes] = useState<string | null>(null);
  const [savedDoc, setSavedDoc] = useState<string | null>(null);
  const recRef = useRef<SpeechRec | null>(null);
  const supported = useRef<boolean>(typeof window !== "undefined" && !!getRecognizer());

  useEffect(() => () => recRef.current?.stop(), []);

  function toggleRecording() {
    if (recording) {
      recRef.current?.stop();
      setRecording(false);
      return;
    }
    const rec = getRecognizer();
    if (!rec) return;
    recRef.current = rec;
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (e) => {
      let finals = "", partial = "";
      for (let i = e.resultIndex; i < (e.results as { length: number }).length; i++) {
        const r = (e.results as ArrayLike<{ 0: { transcript: string }; isFinal: boolean }>)[i];
        if (r.isFinal) finals += r[0].transcript + " ";
        else partial += r[0].transcript;
      }
      if (finals) setTranscript((t) => (t + " " + finals).trim());
      setInterim(partial);
    };
    rec.onend = () => { setRecording(false); setInterim(""); };
    rec.onerror = () => { setRecording(false); setInterim(""); };
    rec.start();
    setRecording(true);
  }

  async function generate() {
    const text = transcript.trim();
    if (text.length < 20 || busy) return;
    setBusy(true);
    setMinutes(null);
    setSavedDoc(null);
    try {
      const r = await apiMeeting(text, title.trim() || "Meeting", save && live);
      setMinutes(r.minutes);
      setSavedDoc(r.doc_id);
    } catch (e) {
      setMinutes(`## Summary\n\nMinutes generation failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <div className="field" style={{ width: 260 }}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Meeting title" placeholder="Meeting title" />
        </div>
        {supported.current && (
          <button className={`btn sm ${recording ? "" : ""}`} onClick={toggleRecording}
                  aria-label={recording ? "Stop recording" : "Start recording"}>
            {recording ? <><CircleStop size={13} style={{ color: "var(--bad)" }} /> Stop</> : <><Mic size={13} /> Record</>}
          </button>
        )}
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-dim)" }}>
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} disabled={!live} />
          Save to Knowledge{!live && " (live mode)"}
        </label>
        <button className="btn primary sm" style={{ marginLeft: "auto" }} onClick={generate}
                disabled={busy || transcript.trim().length < 20}>
          {busy ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />} Generate minutes
        </button>
      </div>

      <div className="app-content meeting-grid">
        <section className="card meeting-col">
          <h3 className="h-display" style={{ fontSize: 12.5, display: "flex", alignItems: "center", gap: 7 }}>
            <Mic size={13} style={{ color: "var(--accent)" }} /> Transcript
            {recording && <span className="pill bad"><span className="dot pulse" style={{ background: "var(--bad)" }} /> recording</span>}
          </h3>
          <textarea
            className="meeting-transcript"
            value={interim ? `${transcript} ${interim}` : transcript}
            onChange={(e) => setTranscript(e.target.value)}
            placeholder={supported.current
              ? "Hit Record and speak, or paste a meeting transcript here…"
              : "Paste a meeting transcript here… (speech recognition not available in this browser)"}
            aria-label="Meeting transcript"
          />
          <span className="faint" style={{ fontSize: 11 }}>{transcript.split(/\s+/).filter(Boolean).length} words</span>
        </section>

        <section className="card meeting-col">
          <h3 className="h-display" style={{ fontSize: 12.5, display: "flex", alignItems: "center", gap: 7 }}>
            <BookOpenCheck size={13} style={{ color: "var(--good)" }} /> Minutes
          </h3>
          {!minutes && !busy && (
            <div className="empty" style={{ margin: "auto" }}>
              <FileText size={24} />
              <p style={{ margin: 0, fontSize: 12.5 }}>Summary, decisions and action items will appear here.</p>
            </div>
          )}
          {busy && <div className="empty" style={{ margin: "auto" }}><Loader2 size={20} className="spin" /> Writing minutes…</div>}
          {minutes && (
            <div className="meeting-minutes">
              {minutes.split("\n").map((line, i) =>
                line.startsWith("## ")
                  ? <h4 key={i}>{line.slice(3)}</h4>
                  : line.startsWith("- ")
                    ? <p key={i} className="mm-bullet">• {line.slice(2)}</p>
                    : line.trim()
                      ? <p key={i}>{line}</p>
                      : null,
              )}
              {savedDoc && <span className="pill good" style={{ marginTop: 8 }}>Saved to Knowledge ✓</span>}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
