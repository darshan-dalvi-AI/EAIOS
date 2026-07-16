/* Video Call — built-in WebRTC calling with AI features.

   · 1:1 calls between online users (signaling over the existing WS hub,
     STUN-only peer connection — works on typical networks, no media server)
   · Live captions (Web Speech) for BOTH sides — captions are exchanged
     over the signaling channel so each participant sees a merged stream
   · Auto Minutes-of-Meeting on hang-up: the merged caption transcript is
     sent through the Meeting agent → summary / decisions / action items,
     optionally saved into the knowledge base
   · Video effects & background changes via a canvas pipeline (the outgoing
     track is ALWAYS the canvas, so switching effects never renegotiates):
     portrait blur, noir, aurora wash, nebula virtual backdrop
   · Screen share (replaceTrack), mute/camera toggles, talk-balance meter */
import {
  BookOpenCheck, Loader2, Mic, MicOff, MonitorUp, Phone, PhoneOff, ScreenShare,
  Sparkles, Video as VideoIcon, VideoOff, Wand2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiMeeting } from "../lib/api";
import { onRtc, sendRtc, type RtcEvent } from "../lib/ws";
import { useOS } from "../store";

type Stage = "idle" | "calling" | "live" | "ended";
type Effect = "none" | "blur" | "noir" | "aurora" | "nebula";

const EFFECTS: { id: Effect; label: string }[] = [
  { id: "none", label: "None" },
  { id: "blur", label: "Portrait blur" },
  { id: "noir", label: "Noir" },
  { id: "aurora", label: "Aurora wash" },
  { id: "nebula", label: "Nebula backdrop" },
];

type SpeechRec = {
  start: () => void; stop: () => void;
  continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> & { length: number } }) => void) | null;
  onend: (() => void) | null; onerror: (() => void) | null;
};

function getRecognizer(): SpeechRec | null {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

export default function VideoApp() {
  const live = useOS((s) => s.live);
  const me = useOS((s) => s.user);
  const online = useOS((s) => s.online);
  const ring = useOS((s) => s.ring);
  const setRing = useOS((s) => s.setRing);

  const [stage, setStage] = useState<Stage>("idle");
  const [peer, setPeer] = useState<{ id: string; name: string; hue: number } | null>(null);
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [effect, setEffect] = useState<Effect>("none");
  const [captionsOn, setCaptionsOn] = useState(true);
  const [captions, setCaptions] = useState<{ who: string; text: string }[]>([]);
  const [talk, setTalk] = useState({ me: 0, them: 0 });
  const [minutes, setMinutes] = useState<string | null>(null);
  const [minutesBusy, setMinutesBusy] = useState(false);
  const [savedDoc, setSavedDoc] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const effectRef = useRef<Effect>("none");
  const localVideo = useRef<HTMLVideoElement>(null);   // hidden raw camera feed
  const stageVideo = useRef<HTMLVideoElement>(null);   // big view (remote in call, processed self otherwise)
  const pipVideo = useRef<HTMLVideoElement>(null);     // small self view (processed)
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rawStream = useRef<MediaStream | null>(null);
  const processed = useRef<MediaStream | null>(null);
  const screenTrack = useRef<MediaStreamTrack | null>(null);
  const pc = useRef<RTCPeerConnection | null>(null);
  const paintTimer = useRef(0); // setInterval, not rAF: keeps rendering when the window is backgrounded
  const rec = useRef<SpeechRec | null>(null);
  const transcript = useRef("");
  const audioCtx = useRef<AudioContext | null>(null);
  const meters = useRef({ me: 0, them: 0, timer: 0 });
  const peerRef = useRef<typeof peer>(null);
  peerRef.current = peer;
  const stageRef = useRef<Stage>("idle");
  stageRef.current = stage; // refs avoid stale closures in speech/RTC callbacks

  /* ── canvas effect pipeline: raw <video> → canvas (~30fps) → captureStream.
     Driven by setInterval (not requestAnimationFrame): rAF is throttled or
     paused when the OS window is backgrounded, which would freeze the outgoing
     video; a timer keeps the pipeline alive regardless. ── */
  function paint() {
    const v = localVideo.current, c = canvasRef.current;
    if (v && c && v.readyState >= 2) {
      const ctx = c.getContext("2d");
      if (ctx) {
        const W = c.width, H = c.height;
        const fx = effectRef.current;
        ctx.save();
        if (fx === "noir") ctx.filter = "grayscale(1) contrast(1.15) brightness(1.05)";
        if (fx === "blur" || fx === "nebula") {
          // background layer
          if (fx === "blur") {
            ctx.filter = "blur(14px) brightness(0.9)";
            ctx.drawImage(v, 0, 0, W, H);
          } else {
            const g = ctx.createLinearGradient(0, 0, W, H);
            g.addColorStop(0, "#0b1030"); g.addColorStop(0.5, "#241b4d"); g.addColorStop(1, "#052030");
            ctx.filter = "none"; ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
            ctx.fillStyle = "rgba(255,255,255,0.5)";
            for (let i = 0; i < 40; i++) {
              const sx = (i * 97) % W, sy = (i * 53) % H;
              ctx.fillRect(sx, sy, 1.5, 1.5);
            }
          }
          // sharp centre-weighted portrait window (approximate person cut-out)
          ctx.filter = "none";
          ctx.beginPath();
          ctx.ellipse(W / 2, H * 0.56, W * 0.30, H * 0.50, 0, 0, Math.PI * 2);
          ctx.clip();
          ctx.drawImage(v, 0, 0, W, H);
        } else {
          ctx.drawImage(v, 0, 0, W, H);
        }
        ctx.restore();
        if (fx === "aurora") {
          const g = ctx.createLinearGradient(0, 0, W, H);
          g.addColorStop(0, "rgba(34,211,238,0.16)");
          g.addColorStop(1, "rgba(139,92,246,0.18)");
          ctx.fillStyle = g;
          ctx.fillRect(0, 0, c.width, c.height);
        }
      }
    }
  }

  async function startMedia(): Promise<boolean> {
    if (rawStream.current) return true;
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: true });
      rawStream.current = s;
      if (localVideo.current) { localVideo.current.srcObject = s; await localVideo.current.play().catch(() => {}); }
      const c = canvasRef.current!;
      c.width = 640; c.height = 480;
      if (!paintTimer.current) paintTimer.current = window.setInterval(paint, 33); // ~30fps
      const canvasStream = c.captureStream(24);
      const out = new MediaStream([...canvasStream.getVideoTracks(), ...s.getAudioTracks()]);
      processed.current = out;
      if (pipVideo.current) { pipVideo.current.srcObject = out; pipVideo.current.play().catch(() => {}); }
      if (stageVideo.current && stage !== "live") { stageVideo.current.srcObject = out; stageVideo.current.play().catch(() => {}); }
      wireMeter(s, "me");
      return true;
    } catch {
      setNote("Camera/mic unavailable — check browser permissions.");
      return false;
    }
  }

  function wireMeter(stream: MediaStream, who: "me" | "them") {
    try {
      audioCtx.current = audioCtx.current || new AudioContext();
      const src = audioCtx.current.createMediaStreamSource(stream);
      const an = audioCtx.current.createAnalyser();
      an.fftSize = 256;
      src.connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      const tick = () => {
        an.getByteFrequencyData(buf);
        const level = buf.reduce((a, b) => a + b, 0) / buf.length;
        if (level > 24) meters.current[who] += 1;
      };
      const t = window.setInterval(tick, 400);
      const old = meters.current.timer;
      if (!old) {
        meters.current.timer = window.setInterval(() => {
          const { me: m, them: th } = meters.current;
          const total = m + th || 1;
          setTalk({ me: Math.round((m / total) * 100), them: Math.round((th / total) * 100) });
        }, 1200) as unknown as number;
      }
      void t;
    } catch { /* meter is best-effort */ }
  }

  /* ── captions (Web Speech) — local finals are shared with the peer ── */
  function startCaptions() {
    if (!captionsOn || rec.current) return;
    const r = getRecognizer();
    if (!r) return;
    rec.current = r;
    r.continuous = true; r.interimResults = false; r.lang = "en-US";
    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (!res.isFinal) continue;
        const text = res[0].transcript.trim();
        if (!text) continue;
        pushCaption("You", text);
        transcript.current += `${me?.full_name ?? "Me"}: ${text}. `;
        const p = peerRef.current;
        if (p) sendRtc("rtc.caption", p.id, { text });
      }
    };
    r.onend = () => { if (rec.current === r && stageRef.current === "live") { try { r.start(); } catch { /* restart race */ } } };
    r.onerror = () => {};
    try { r.start(); } catch { /* already running */ }
  }

  function stopCaptions() {
    rec.current?.stop();
    rec.current = null;
  }

  function pushCaption(who: string, text: string) {
    setCaptions((c) => [...c.slice(-5), { who, text }]);
  }

  /* ── WebRTC ── */
  function newPc(targetId: string): RTCPeerConnection {
    const conn = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
    processed.current?.getTracks().forEach((t) => conn.addTrack(t, processed.current!));
    conn.onicecandidate = (e) => { if (e.candidate) sendRtc("rtc.ice", targetId, { candidate: e.candidate.toJSON() }); };
    conn.ontrack = (e) => {
      const [stream] = e.streams;
      if (stageVideo.current && stream) {
        stageVideo.current.srcObject = stream;
        stageVideo.current.play().catch(() => {});
        wireMeter(stream, "them");
      }
    };
    pc.current = conn;
    return conn;
  }

  async function call(target: { id: string; name: string; hue: number }) {
    if (!(await startMedia())) return;
    setPeer(target);
    setStage("calling");
    setNote("");
    sendRtc("rtc.ring", target.id, { call: "video" });
  }

  async function accept() {
    if (!ring) return;
    const caller = ring; // capture before any state change
    if (!(await startMedia())) return;
    // Order matters: go live BEFORE clearing the ring. The incoming overlay is
    // derived from `ring`, so clearing it here simply hides the overlay.
    setPeer(caller);
    setStage("live");
    startCaptions();
    sendRtc("rtc.accept", caller.id, {});
    setRing(null);
  }

  function decline() {
    if (ring) sendRtc("rtc.decline", ring.id, {});
    setRing(null);
  }

  function hangup(sendEnd = true) {
    const p = peerRef.current;
    if (sendEnd && p) sendRtc("rtc.end", p.id, {});
    pc.current?.close();
    pc.current = null;
    stopCaptions();
    setSharing(false);
    screenTrack.current?.stop();
    screenTrack.current = null;
    setStage(transcript.current.trim().length > 40 ? "ended" : "idle");
    if (transcript.current.trim().length > 40) void makeMinutes();
    if (stageVideo.current && processed.current) {
      stageVideo.current.srcObject = processed.current;
      stageVideo.current.play().catch(() => {});
    }
  }

  async function makeMinutes() {
    setMinutesBusy(true);
    try {
      const r = await apiMeeting(transcript.current, `Video call with ${peerRef.current?.name ?? "peer"}`, live);
      setMinutes(r.minutes);
      setSavedDoc(r.doc_id);
    } catch (e) {
      setMinutes(`## Summary\n\nMoM generation failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setMinutesBusy(false);
    }
  }

  /* ── signaling reactions ── */
  useEffect(() => {
    const off = onRtc(async (ev: RtcEvent) => {
      const from = ev.from;
      switch (ev.type) {
        case "rtc.accept": {
          if (stage !== "calling" || !from) return;
          setStage("live");
          startCaptions();
          const conn = newPc(from.id);
          const offer = await conn.createOffer();
          await conn.setLocalDescription(offer);
          sendRtc("rtc.offer", from.id, { sdp: conn.localDescription });
          break;
        }
        case "rtc.offer": {
          if (!from) return;
          const conn = newPc(from.id);
          await conn.setRemoteDescription(ev.payload.sdp as RTCSessionDescriptionInit);
          const answer = await conn.createAnswer();
          await conn.setLocalDescription(answer);
          sendRtc("rtc.answer", from.id, { sdp: conn.localDescription });
          break;
        }
        case "rtc.answer":
          await pc.current?.setRemoteDescription(ev.payload.sdp as RTCSessionDescriptionInit);
          break;
        case "rtc.ice":
          try { await pc.current?.addIceCandidate(ev.payload.candidate as RTCIceCandidateInit); } catch { /* late ice */ }
          break;
        case "rtc.caption":
          if (from) {
            pushCaption(from.name, String(ev.payload.text ?? ""));
            transcript.current += `${from.name}: ${ev.payload.text}. `;
          }
          break;
        case "rtc.decline":
          setNote(`${from?.name ?? "Callee"} declined the call.`);
          setStage("idle");
          break;
        case "rtc.unavailable":
          setNote("That user just went offline.");
          setStage("idle");
          break;
        case "rtc.end":
          hangup(false);
          break;
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  // The incoming-call overlay is derived from `ring` directly (see render),
  // so there is no separate "incoming" stage to keep in sync — this avoids a
  // state race where clearing the ring on accept could reset us to idle.
  const incoming = !!ring && stage !== "live" && stage !== "calling";

  useEffect(() => {
    effectRef.current = effect;
  }, [effect]);

  // demo mode / solo studio: start the camera immediately for effect preview
  useEffect(() => {
    void startMedia();
    return () => {
      if (paintTimer.current) window.clearInterval(paintTimer.current);
      stopCaptions();
      pc.current?.close();
      rawStream.current?.getTracks().forEach((t) => t.stop());
      screenTrack.current?.stop();
      if (meters.current.timer) window.clearInterval(meters.current.timer);
      audioCtx.current?.close().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleMic() {
    rawStream.current?.getAudioTracks().forEach((t) => (t.enabled = !micOn));
    setMicOn(!micOn);
  }

  function toggleCam() {
    rawStream.current?.getVideoTracks().forEach((t) => (t.enabled = !camOn));
    setCamOn(!camOn);
  }

  async function toggleShare() {
    if (sharing) {
      screenTrack.current?.stop();
      screenTrack.current = null;
      const camTrack = processed.current?.getVideoTracks()[0];
      const sender = pc.current?.getSenders().find((s) => s.track?.kind === "video");
      if (sender && camTrack) await sender.replaceTrack(camTrack);
      setSharing(false);
      return;
    }
    try {
      const disp = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const track = disp.getVideoTracks()[0];
      screenTrack.current = track;
      const sender = pc.current?.getSenders().find((s) => s.track?.kind === "video");
      if (sender) await sender.replaceTrack(track);
      track.onended = () => void toggleShare();
      setSharing(true);
    } catch { /* user cancelled */ }
  }

  const roster = online.filter((u) => u.id !== me?.id);
  const inCall = stage === "live" || stage === "calling";

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <span className="pill info"><VideoIcon size={11} /> {live ? "signaling online" : "demo — solo studio"}</span>
        {stage === "live" && peer && <span className="pill good">in call with {peer.name}</span>}
        {stage === "calling" && peer && <span className="pill warn"><Loader2 size={11} className="spin" /> calling {peer.name}…</span>}
        {note && <span className="pill warn">{note}</span>}
        <span style={{ marginLeft: "auto" }} className="faint" title="Talk-time balance">
          🗣 you {talk.me}% · them {talk.them}%
        </span>
      </div>

      <div className="app-content vc-layout">
        {/* main stage */}
        <div className="vc-stage-wrap">
          <video ref={stageVideo} className="vc-stage" muted={stage !== "live"} playsInline />
          <video ref={pipVideo} className={`vc-pip ${inCall ? "" : "hidden"}`} muted playsInline />
          {/* raw feed + processing canvas are kept off-screen but RENDERED —
              a display:none canvas won't produce a captureStream in some browsers */}
          <video ref={localVideo} className="vc-offscreen" muted playsInline />
          <canvas ref={canvasRef} className="vc-offscreen" />

          {captionsOn && captions.length > 0 && (
            <div className="vc-captions">
              {captions.slice(-3).map((c, i) => (
                <div key={i}><b>{c.who}:</b> {c.text}</div>
              ))}
            </div>
          )}

          {incoming && ring && (
            <div className="vc-ring">
              <span className="avatar" style={{ "--hue": ring.hue } as React.CSSProperties}>
                {ring.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
              </span>
              <b>{ring.name} is calling…</b>
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn primary sm" onClick={accept}><Phone size={13} /> Accept</button>
                <button className="btn sm" onClick={decline}><PhoneOff size={13} /> Decline</button>
              </div>
            </div>
          )}

          {/* controls */}
          <div className="vc-controls">
            <button className={`vc-btn ${micOn ? "" : "off"}`} onClick={toggleMic} aria-label={micOn ? "Mute microphone" : "Unmute microphone"}>
              {micOn ? <Mic size={16} /> : <MicOff size={16} />}
            </button>
            <button className={`vc-btn ${camOn ? "" : "off"}`} onClick={toggleCam} aria-label={camOn ? "Turn camera off" : "Turn camera on"}>
              {camOn ? <VideoIcon size={16} /> : <VideoOff size={16} />}
            </button>
            <button className={`vc-btn ${sharing ? "on" : ""}`} onClick={toggleShare} disabled={stage !== "live"} aria-label="Share screen" title="Share screen">
              {sharing ? <MonitorUp size={16} /> : <ScreenShare size={16} />}
            </button>
            <button className={`vc-btn ${captionsOn ? "on" : ""}`} onClick={() => { setCaptionsOn(!captionsOn); captionsOn ? stopCaptions() : (stage === "live" && startCaptions()); }}
                    aria-label="Toggle live captions" title="Live captions">CC</button>
            {stage === "live" || stage === "calling"
              ? <button className="vc-btn danger" onClick={() => hangup()} aria-label="End call"><PhoneOff size={16} /></button>
              : null}
          </div>
        </div>

        {/* side panel */}
        <aside className="vc-side">
          <div className="palette-section" style={{ padding: "0 0 6px", display: "flex", gap: 6, alignItems: "center" }}>
            <Wand2 size={12} /> Effects & background
          </div>
          <div className="vc-effects">
            {EFFECTS.map((f) => (
              <button key={f.id} className={`btn sm ${effect === f.id ? "primary" : ""}`} onClick={() => setEffect(f.id)}>
                {f.label}
              </button>
            ))}
          </div>

          <div className="palette-section" style={{ padding: "12px 0 6px" }}>Call someone</div>
          {!live && <p className="faint" style={{ fontSize: 11.5, margin: 0 }}>Calls need the live backend (two logged-in users). Demo mode still gives you camera, effects, captions and MoM.</p>}
          {live && roster.length === 0 && <p className="faint" style={{ fontSize: 11.5, margin: 0 }}>No one else is online. Open a second browser (or incognito) and log in as maya@eaios.dev to test.</p>}
          {roster.map((u) => (
            <div key={u.id} className="vc-roster-row">
              <span className="avatar sm" style={{ "--hue": u.hue } as React.CSSProperties}>
                {u.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
              </span>
              <span style={{ fontSize: 12.5, fontWeight: 600 }}>{u.name}</span>
              <button className="btn primary sm" style={{ marginLeft: "auto" }} disabled={inCall} onClick={() => call(u)}>
                <Phone size={12} /> Call
              </button>
            </div>
          ))}

          {(stage === "ended" || minutes || minutesBusy) && (
            <>
              <div className="palette-section" style={{ padding: "12px 0 6px", display: "flex", gap: 6, alignItems: "center" }}>
                <BookOpenCheck size={12} /> Minutes of meeting
              </div>
              {minutesBusy && <p className="faint" style={{ fontSize: 12 }}><Loader2 size={12} className="spin" /> Writing MoM from the call captions…</p>}
              {minutes && (
                <div className="meeting-minutes" style={{ maxHeight: 240 }}>
                  {minutes.split("\n").map((line, i) =>
                    line.startsWith("## ") ? <h4 key={i}>{line.slice(3)}</h4>
                      : line.startsWith("- ") ? <p key={i} className="mm-bullet">• {line.slice(2)}</p>
                      : line.trim() ? <p key={i}>{line}</p> : null,
                  )}
                  {savedDoc && <span className="pill good" style={{ marginTop: 6 }}>Saved to Knowledge ✓</span>}
                </div>
              )}
            </>
          )}

          <p className="faint" style={{ fontSize: 10.5, marginTop: "auto", lineHeight: 1.5 }}>
            <Sparkles size={10} /> Captions run locally in your browser; on hang-up they become
            AI minutes via the Meeting agent. P2P media never touches the server.
          </p>
        </aside>
      </div>
    </div>
  );
}
