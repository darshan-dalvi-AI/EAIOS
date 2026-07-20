/* "Hey EAIOS" wake word — optional (Settings → toggle). Listens continuously
   with the Web Speech API; on the phrase, chimes, opens Chat and starts
   voice input via the chat draft. */
import { useEffect, useRef } from "react";
import { useOS } from "../store";

const PHRASES = ["hey eaios", "hey e aios", "hey ai os", "hey a os", "hey ayos", "hey eos"];

export default function WakeWord() {
  const open = useOS((s) => s.open);
  const pushFeed = useOS((s) => s.pushFeed);
  const rec = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    const w = window as unknown as { webkitSpeechRecognition?: new () => any; SpeechRecognition?: new () => any };
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return;
    let alive = true;
    const r = new Ctor();
    rec.current = r;
    r.continuous = true;
    r.interimResults = false;
    r.lang = "en-US";
    r.onresult = (e: { resultIndex: number; results: ArrayLike<{ 0: { transcript: string } }> & { length: number } }) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const heard = e.results[i][0].transcript.toLowerCase();
        if (PHRASES.some((p) => heard.includes(p))) {
          try { // soft chime
            const ctx = new AudioContext();
            const o = ctx.createOscillator(); const g = ctx.createGain();
            o.frequency.value = 880; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination);
            o.start(); o.stop(ctx.currentTime + 0.18);
          } catch { /* no audio */ }
          open("chat");
          pushFeed({ agent: "voice", text: "🎙️ Wake word detected — EAIOS is listening.", kind: "system" });
        }
      }
    };
    r.onend = () => { if (alive) { try { r.start(); } catch { /* busy */ } } };
    r.onerror = () => { /* mic denied or in use — silently idle */ };
    try { r.start(); } catch { /* already running */ }
    return () => { alive = false; try { r.stop(); } catch { /* noop */ } };
  }, [open, pushFeed]);

  return null;
}
