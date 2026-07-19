/* Video Call — built-in WebRTC calling with AI features.

   · Multi-party mesh calls (start a call, invite more people; each joiner
     offers to everyone already in the room → full mesh). Signaling rides the
     existing WS hub as point-to-point rtc.* frames; media is P2P (STUN only).
   · Live captions (Web Speech) exchanged with peers → one merged transcript.
   · Minutes-of-Meeting: generate them live mid-call ("MoM now") or auto on
     hang-up — the transcript goes through the Meeting agent (summary /
     decisions / action items), optionally saved to the knowledge base.
   · Virtual backgrounds & effects via a canvas pipeline (blur / noir / aurora
     / nebula) — the outgoing track is always the canvas, so switching effects
     never renegotiates. Screen share (replaceTrack), mute/camera, talk meter. */
import {
  BookOpenCheck, Loader2, Mic, MicOff, MonitorUp, Phone, PhoneOff, ScreenShare,
  Sparkles, UserPlus, Video as VideoIcon, VideoOff, Wand2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiMeeting } from "../lib/api";
import { onRtc, sendRtc, type RtcEvent } from "../lib/ws";
import { useOS } from "../store";

type Stage = "idle" | "calling" | "live" | "ended";
type Effect = "none" | "blur" | "noir" | "aurora" | "nebula";
type Person = { id: string; name: string; hue: number };

const EFFECTS: { id: Effect; label: string }[] = [
  { id: "none", label: "None" }, { id: "blur", label: "Portrait blur" },
  { id: "noir", label: "Noir" }, { id: "aurora", label: "Aurora wash" }, { id: "nebula", label: "Nebula backdrop" },
];

type SpeechRec = {
  start: () => void; stop: () => void; continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> & { length: number } }) => void) | null;
  onend: (() => void) | null; onerror: (() => void) | null;
};
function getRecognizer(): SpeechRec | null {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec };
  const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}
const ICE = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };

export default function VideoApp() {
  const live = useOS((s) => s.live);
  const me = useOS((s) => s.user);
  const online = useOS((s) => s.online);
  const ring = useOS((s) => s.ring);
  const setRing = useOS((s) => s.setRing);

  const [stage, setStage] = useState<Stage>("idle");
  const [members, setMembers] = useState<Person[]>([]);        // remote participants in the room
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);
  const [sharing, setSharing] = useState(false);
  const [effect, setEffect] = useState<Effect>("none");
  const [captionsOn, setCaptionsOn] = useState(true);
  const [captions, setCaptions] = useState<{ who: string; text: string }[]>([]);
  const [minutes, setMinutes] = useState<string | null>(null);
  const [minutesBusy, setMinutesBusy] = useState(false);
  const [savedDoc, setSavedDoc] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const effectRef = useRef<Effect>("none");
  const localVideo = useRef<HTMLVideoElement>(null);
  const selfPip = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rawStream = useRef<MediaStream | null>(null);
  const processed = useRef<MediaStream | null>(null);
  const screenTrack = useRef<MediaStreamTrack | null>(null);
  const peers = useRef<Map<string, RTCPeerConnection>>(new Map());   // userId → connection
  const remoteEls = useRef<Map<string, HTMLVideoElement | null>>(new Map());
  const paintTimer = useRef(0);
  const rec = useRef<SpeechRec | null>(null);
  const transcript = useRef("");
  const audioCtx = useRef<AudioContext | null>(null);
  const membersRef = useRef<Person[]>([]);
  membersRef.current = members;
  const stageRef = useRef<Stage>("idle");
  stageRef.current = stage;

  /* ── canvas effect pipeline ── */
  function paint() {
    const v = localVideo.current, c = canvasRef.current;
    if (v && c && v.readyState >= 2) {
      const ctx = c.getContext("2d");
      if (ctx) {
        const W = c.width, H = c.height, fx = effectRef.current;
        ctx.save();
        if (fx === "noir") ctx.filter = "grayscale(1) contrast(1.15) brightness(1.05)";
        if (fx === "blur" || fx === "nebula") {
          if (fx === "blur") { ctx.filter = "blur(14px) brightness(0.9)"; ctx.drawImage(v, 0, 0, W, H); }
          else {
            const g = ctx.createLinearGradient(0, 0, W, H);
            g.addColorStop(0, "#0b1030"); g.addColorStop(0.5, "#241b4d"); g.addColorStop(1, "#052030");
            ctx.filter = "none"; ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
            ctx.fillStyle = "rgba(255,255,255,0.5)";
            for (let i = 0; i < 40; i++) ctx.fillRect((i * 97) % W, (i * 53) % H, 1.5, 1.5);
          }
          ctx.filter = "none"; ctx.beginPath();
          ctx.ellipse(W / 2, H * 0.56, W * 0.30, H * 0.50, 0, 0, Math.PI * 2); ctx.clip();
          ctx.drawImage(v, 0, 0, W, H);
        } else ctx.drawImage(v, 0, 0, W, H);
        ctx.restore();
        if (fx === "aurora") {
          const g = ctx.createLinearGradient(0, 0, W, H);
          g.addColorStop(0, "rgba(34,211,238,0.16)"); g.addColorStop(1, "rgba(139,92,246,0.18)");
          ctx.fillStyle = g; ctx.fillRect(0, 0, c.width, c.height);
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
      if (!paintTimer.current) paintTimer.current = window.setInterval(paint, 33);
      const canvasStream = c.captureStream(24);
      const out = new MediaStream([...canvasStream.getVideoTracks(), ...s.getAudioTracks()]);
      processed.current = out;
      if (selfPip.current) { selfPip.current.srcObject = out; selfPip.current.play().catch(() => {}); }
      wireMeter(s);
      return true;
    } catch { setNote("Camera/mic unavailable — check browser permissions."); return false; }
  }

  function wireMeter(stream: MediaStream) {
    try {
      audioCtx.current = audioCtx.current || new AudioContext();
      const src = audioCtx.current.createMediaStreamSource(stream);
      const an = audioCtx.current.createAnalyser(); an.fftSize = 256; src.connect(an);
    } catch { /* best effort */ }
  }

  /* ── captions ── */
  function startCaptions() {
    if (!captionsOn || rec.current) return;
    const r = getRecognizer(); if (!r) return;
    rec.current = r; r.continuous = true; r.interimResults = false; r.lang = "en-US";
    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i]; if (!res.isFinal) continue;
        const text = res[0].transcript.trim(); if (!text) continue;
        pushCaption("You", text);
        transcript.current += `${me?.full_name ?? "Me"}: ${text}. `;
        membersRef.current.forEach((p) => sendRtc("rtc.caption", p.id, { text }));
      }
    };
    r.onend = () => { if (rec.current === r && stageRef.current === "live") { try { r.start(); } catch { /* race */ } } };
    r.onerror = () => {};
    try { r.start(); } catch { /* running */ }
  }
  function stopCaptions() { rec.current?.stop(); rec.current = null; }
  function pushCaption(who: string, text: string) { setCaptions((c) => [...c.slice(-5), { who, text }]); }

  /* ── mesh WebRTC ── */
  function attachRemote(id: string, stream: MediaStream) {
    const el = remoteEls.current.get(id);
    if (el) { el.srcObject = stream; el.play().catch(() => {}); }
  }
  function newPc(target: Person): RTCPeerConnection {
    const existing = peers.current.get(target.id);
    if (existing) return existing;
    const conn = new RTCPeerConnection(ICE);
    processed.current?.getTracks().forEach((t) => conn.addTrack(t, processed.current!));
    conn.onicecandidate = (e) => { if (e.candidate) sendRtc("rtc.ice", target.id, { candidate: e.candidate.toJSON() }); };
    conn.ontrack = (e) => { const [stream] = e.streams; if (stream) { requestAnimationFrame(() => attachRemote(target.id, stream)); } };
    peers.current.set(target.id, conn);
    setMembers((m) => (m.some((x) => x.id === target.id) ? m : [...m, target]));
    return conn;
  }
  async function offerTo(target: Person) {
    const conn = newPc(target);
    const offer = await conn.createOffer();
    await conn.setLocalDescription(offer);
    sendRtc("rtc.offer", target.id, { sdp: conn.localDescription });
  }

  async function call(target: Person) {
    if (!(await startMedia())) return;
    setNote("");
    if (stage !== "live") setStage("calling");
    // roster we send = everyone currently in the room + me
    const roster = [...membersRef.current, ...(me ? [{ id: me.id, name: me.full_name, hue: me.avatar_hue }] : [])];
    sendRtc("rtc.ring", target.id, { roster });
  }

  async function accept() {
    if (!ring) return;
    const rosterFromRing = (ringRosterRef.current || []).filter((p) => p.id !== me?.id);
    if (!(await startMedia())) return;
    setStage("live");
    startCaptions();
    // joiner offers to EVERYONE already in the room (full mesh)
    const roomPeople: Person[] = rosterFromRing.length ? rosterFromRing : [ring];
    for (const p of roomPeople) { await offerTo(p); }
    sendRtc("rtc.accept", ring.id, {});
    setRing(null);
  }
  function decline() { if (ring) sendRtc("rtc.decline", ring.id, {}); setRing(null); }

  const ringRosterRef = useRef<Person[] | null>(null);

  function leaveAll(sendEnd = true) {
    if (sendEnd) membersRef.current.forEach((p) => sendRtc("rtc.end", p.id, {}));
    peers.current.forEach((c) => c.close());
    peers.current.clear();
    remoteEls.current.clear();
    setMembers([]);
    stopCaptions();
    setSharing(false);
    screenTrack.current?.stop(); screenTrack.current = null;
    const hasTranscript = transcript.current.trim().length > 40;
    setStage(hasTranscript ? "ended" : "idle");
    if (hasTranscript) void makeMinutes();
  }

  async function makeMinutes(liveMid = false) {
    if (transcript.current.trim().length < 20) { setNote("Not enough captions yet for minutes."); return; }
    setMinutesBusy(true);
    try {
      const title = `Video call${members.length ? ` with ${members.map((m) => m.name).join(", ")}` : ""}`;
      const r = await apiMeeting(transcript.current, title, live);
      setMinutes(r.minutes); setSavedDoc(r.doc_id);
      if (liveMid) setNote("Minutes updated from the call so far.");
    } catch (e) { setMinutes(`## Summary\n\nMoM generation failed: ${e instanceof Error ? e.message : e}`); }
    finally { setMinutesBusy(false); }
  }

  /* ── signaling ── */
  useEffect(() => {
    const off = onRtc(async (ev: RtcEvent) => {
      const from = ev.from as Person | undefined;
      switch (ev.type) {
        case "rtc.accept":
          if (stage === "calling") setStage("live");
          if (from) startCaptions();
          break;
        case "rtc.offer": {
          if (!from) return;
          const conn = newPc(from);
          await conn.setRemoteDescription(ev.payload.sdp as RTCSessionDescriptionInit);
          const answer = await conn.createAnswer();
          await conn.setLocalDescription(answer);
          sendRtc("rtc.answer", from.id, { sdp: conn.localDescription });
          if (stageRef.current !== "live") { setStage("live"); startCaptions(); }
          break;
        }
        case "rtc.answer":
          if (from) await peers.current.get(from.id)?.setRemoteDescription(ev.payload.sdp as RTCSessionDescriptionInit);
          break;
        case "rtc.ice":
          if (from) { try { await peers.current.get(from.id)?.addIceCandidate(ev.payload.candidate as RTCIceCandidateInit); } catch { /* late */ } }
          break;
        case "rtc.caption":
          if (from) { pushCaption(from.name, String(ev.payload.text ?? "")); transcript.current += `${from.name}: ${ev.payload.text}. `; }
          break;
        case "rtc.decline": setNote(`${from?.name ?? "Callee"} declined.`); if (!membersRef.current.length) setStage("idle"); break;
        case "rtc.unavailable": setNote("That user is offline."); if (!membersRef.current.length) setStage("idle"); break;
        case "rtc.end":
          if (from) {
            peers.current.get(from.id)?.close(); peers.current.delete(from.id);
            remoteEls.current.delete(from.id);
            const rest = membersRef.current.filter((p) => p.id !== from.id);
            setMembers(rest);
            if (!rest.length) leaveAll(false);
          }
          break;
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  // capture the ring's roster (people already in the call) for mesh join
  useEffect(() => {
    if (ring) {
      const r = (ring as unknown as { roster?: Person[] }).roster;
      ringRosterRef.current = Array.isArray(r) ? r : [ring];
    } else ringRosterRef.current = null;
  }, [ring]);

  const incoming = !!ring && stage !== "live" && stage !== "calling";

  useEffect(() => { effectRef.current = effect; }, [effect]);
  useEffect(() => {
    void startMedia();
    return () => {
      if (paintTimer.current) window.clearInterval(paintTimer.current);
      stopCaptions();
      peers.current.forEach((c) => c.close());
      rawStream.current?.getTracks().forEach((t) => t.stop());
      screenTrack.current?.stop();
      audioCtx.current?.close().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleMic() { rawStream.current?.getAudioTracks().forEach((t) => (t.enabled = !micOn)); setMicOn(!micOn); }
  function toggleCam() { rawStream.current?.getVideoTracks().forEach((t) => (t.enabled = !camOn)); setCamOn(!camOn); }
  async function toggleShare() {
    if (sharing) {
      screenTrack.current?.stop(); screenTrack.current = null;
      const camTrack = processed.current?.getVideoTracks()[0];
      peers.current.forEach((c) => { const s = c.getSenders().find((x) => x.track?.kind === "video"); if (s && camTrack) void s.replaceTrack(camTrack); });
      setSharing(false); return;
    }
    try {
      const disp = await navigator.mediaDevices.getDisplayMedia({ video: true });
      const track = disp.getVideoTracks()[0]; screenTrack.current = track;
      peers.current.forEach((c) => { const s = c.getSenders().find((x) => x.track?.kind === "video"); if (s) void s.replaceTrack(track); });
      track.onended = () => void toggleShare();
      setSharing(true);
    } catch { /* cancelled */ }
  }

  const roster = online.filter((u) => u.id !== me?.id);
  const inCall = stage === "live" || stage === "calling";
  const tileCount = members.length + 1;
  const cols = tileCount <= 1 ? 1 : tileCount <= 4 ? 2 : 3;

  return (
    <div className="app-pane">
      <div className="app-toolbar">
        <span className="pill info"><VideoIcon size={11} /> {live ? "signaling online" : "demo — solo studio"}</span>
        {stage === "live" && <span className="pill good">{members.length ? `${members.length + 1}-way call` : "camera live"}</span>}
        {stage === "calling" && <span className="pill warn"><Loader2 size={11} className="spin" /> ringing…</span>}
        {note && <span className="pill warn">{note}</span>}
        {stage === "live" && (
          <button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => makeMinutes(true)} disabled={minutesBusy}>
            {minutesBusy ? <Loader2 size={12} className="spin" /> : <BookOpenCheck size={12} />} MoM now
          </button>
        )}
      </div>

      <div className="app-content vc-layout">
        <div className="vc-stage-wrap">
          {/* participant grid */}
          <div className="vc-grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
            <div className="vc-tile">
              <video ref={selfPip} className="vc-tile-vid" muted playsInline />
              <span className="vc-name">You{sharing ? " · sharing" : ""}</span>
            </div>
            {members.map((p) => (
              <div className="vc-tile" key={p.id}>
                <video ref={(el) => remoteEls.current.set(p.id, el)} className="vc-tile-vid" playsInline autoPlay />
                <span className="vc-name" style={{ borderLeft: `3px solid hsl(${p.hue},80%,55%)` }}>{p.name}</span>
              </div>
            ))}
          </div>
          <video ref={localVideo} className="vc-offscreen" muted playsInline />
          <canvas ref={canvasRef} className="vc-offscreen" />

          {captionsOn && captions.length > 0 && (
            <div className="vc-captions">
              {captions.slice(-3).map((c, i) => <div key={i}><b>{c.who}:</b> {c.text}</div>)}
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

          <div className="vc-controls">
            <button className={`vc-btn ${micOn ? "" : "off"}`} onClick={toggleMic} aria-label={micOn ? "Mute microphone" : "Unmute microphone"}>{micOn ? <Mic size={16} /> : <MicOff size={16} />}</button>
            <button className={`vc-btn ${camOn ? "" : "off"}`} onClick={toggleCam} aria-label={camOn ? "Turn camera off" : "Turn camera on"}>{camOn ? <VideoIcon size={16} /> : <VideoOff size={16} />}</button>
            <button className={`vc-btn ${sharing ? "on" : ""}`} onClick={toggleShare} disabled={stage !== "live"} aria-label="Share screen" title="Share screen">{sharing ? <MonitorUp size={16} /> : <ScreenShare size={16} />}</button>
            <button className={`vc-btn ${captionsOn ? "on" : ""}`} onClick={() => { setCaptionsOn(!captionsOn); captionsOn ? stopCaptions() : (stage === "live" && startCaptions()); }} aria-label="Toggle live captions" title="Live captions">CC</button>
            {inCall ? <button className="vc-btn danger" onClick={() => leaveAll()} aria-label="Leave call"><PhoneOff size={16} /></button> : null}
          </div>
        </div>

        <aside className="vc-side">
          <div className="palette-section" style={{ padding: "0 0 6px", display: "flex", gap: 6, alignItems: "center" }}><Wand2 size={12} /> Effects & background</div>
          <div className="vc-effects">
            {EFFECTS.map((f) => <button key={f.id} className={`btn sm ${effect === f.id ? "primary" : ""}`} onClick={() => setEffect(f.id)}>{f.label}</button>)}
          </div>

          <div className="palette-section" style={{ padding: "12px 0 6px" }}>{stage === "live" ? "Invite to this call" : "Call someone"}</div>
          {!live && <p className="faint" style={{ fontSize: 11.5, margin: 0 }}>Calls need the live backend (two logged-in users). Demo mode still gives you camera, effects, captions and MoM.</p>}
          {live && roster.length === 0 && <p className="faint" style={{ fontSize: 11.5, margin: 0 }}>No one else is online. Open a second browser (incognito) and log in as maya@eaios.dev to test.</p>}
          {roster.map((u) => {
            const inRoom = members.some((m) => m.id === u.id);
            return (
              <div key={u.id} className="vc-roster-row">
                <span className="avatar sm" style={{ "--hue": u.hue } as React.CSSProperties}>{u.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}</span>
                <span style={{ fontSize: 12.5, fontWeight: 600 }}>{u.name}</span>
                {inRoom
                  ? <span className="pill good" style={{ marginLeft: "auto" }}>in call</span>
                  : <button className="btn primary sm" style={{ marginLeft: "auto" }} onClick={() => call({ id: u.id, name: u.name, hue: u.hue })}>
                      {stage === "live" ? <><UserPlus size={12} /> Add</> : <><Phone size={12} /> Call</>}
                    </button>}
              </div>
            );
          })}

          {(stage === "ended" || minutes || minutesBusy) && (
            <>
              <div className="palette-section" style={{ padding: "12px 0 6px", display: "flex", gap: 6, alignItems: "center" }}><BookOpenCheck size={12} /> Minutes of meeting</div>
              {minutesBusy && <p className="faint" style={{ fontSize: 12 }}><Loader2 size={12} className="spin" /> Writing MoM from the call captions…</p>}
              {minutes && (
                <div className="meeting-minutes" style={{ maxHeight: 240 }}>
                  {minutes.split("\n").map((line, i) =>
                    line.startsWith("## ") ? <h4 key={i}>{line.slice(3)}</h4>
                      : line.startsWith("- ") ? <p key={i} className="mm-bullet">• {line.slice(2)}</p>
                      : line.trim() ? <p key={i}>{line}</p> : null)}
                  {savedDoc && <span className="pill good" style={{ marginTop: 6 }}>Saved to Knowledge ✓</span>}
                </div>
              )}
            </>
          )}

          <p className="faint" style={{ fontSize: 10.5, marginTop: "auto", lineHeight: 1.5 }}>
            <Sparkles size={10} /> Captions run locally; generate minutes any time with “MoM now” or on hang-up. P2P media never touches the server.
          </p>
        </aside>
      </div>
    </div>
  );
}
