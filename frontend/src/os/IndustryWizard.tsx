/* Industry personalisation — the first thing a new company sees.
   An empty AI workspace asks the customer to imagine what it could do for
   their business, and most never get there. This asks one question instead,
   then configures the workspace in front of them: specialist agents written
   for their field, the questions their staff actually ask, and an intake
   automation. Shown once per workspace, to the admin only. */
import {
  ArrowRight, Bot, Briefcase, Building2, Check, Factory, GraduationCap, HeartPulse,
  Landmark, Loader2, Scale, ShoppingBag, Sparkles, Users, Workflow, Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { apiIndustries, apiSetIndustry, type Industry } from "../lib/api";
import { useOS } from "../store";

const ICONS: Record<string, typeof Bot> = {
  Briefcase, HeartPulse, Scale, Landmark, Users, Factory,
  GraduationCap, Building2, ShoppingBag, Sparkles,
};

type Phase = "pick" | "confirm" | "applying" | "done";

export default function IndustryWizard() {
  const { user, orgName, industry, setIndustry, live, open } = useOS();
  const [list, setList] = useState<Industry[] | null>(null);
  const [chosen, setChosen] = useState<Industry | null>(null);
  const [phase, setPhase] = useState<Phase>("pick");
  const [result, setResult] = useState<{ agents_created: string[]; workflows_created: string[] } | null>(null);
  const [err, setErr] = useState("");
  const [dismissed, setDismissed] = useState(false);

  // Only the admin of a workspace that has never answered the question.
  const shouldAsk = user?.role === "admin" && !industry && !dismissed;

  useEffect(() => {
    if (!shouldAsk || list) return;
    apiIndustries().then(setList).catch(() => setDismissed(true));   // offline → never block
  }, [shouldAsk, list]);

  // Dismissal always wins. Otherwise: once the workspace is configured
  // `industry` is set, which would normally hide this component — but that
  // would snatch away the confirmation screen at the exact moment it matters,
  // so the "done" phase keeps rendering until the user moves on.
  if (dismissed || !list) return null;
  if (!shouldAsk && phase !== "done") return null;

  async function apply() {
    if (!chosen) return;
    setPhase("applying");
    setErr("");
    try {
      // In demo mode there is no backend to configure; still show the outcome
      // so the flow can be demonstrated end to end.
      const r = live
        ? await apiSetIndustry(chosen.id)
        : { agents_created: chosen.agents.map((a) => a.name), workflows_created: [chosen.workflow] };
      setResult(r);
      setIndustry(chosen.id);
      setPhase("done");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not configure the workspace");
      setPhase("confirm");
    }
  }

  return (
    <div className="iw-backdrop" role="dialog" aria-modal="true" aria-label="Set up your workspace">
      <div className="iw">
        {/* ── step 1: the question ── */}
        {phase === "pick" && (
          <>
            <header className="iw-head">
              <span className="iw-step">Step 1 of 2</span>
              <h2>What does {orgName || "your company"} do?</h2>
              <p>
                EAIOS configures itself for your field — specialist AI agents, the questions your
                team actually asks, and an automation for your most repetitive task. This takes
                one click and you can change everything afterwards.
              </p>
            </header>
            <div className="iw-grid">
              {list.map((ind) => {
                const Icon = ICONS[ind.icon] ?? Sparkles;
                return (
                  <button
                    key={ind.id}
                    className={`iw-card ${chosen?.id === ind.id ? "on" : ""}`}
                    style={{ "--hue": ind.hue } as React.CSSProperties}
                    onClick={() => setChosen(ind)}
                    data-industry={ind.id}
                  >
                    <span className="iw-ico"><Icon size={19} /></span>
                    <b>{ind.name}</b>
                    <span className="iw-tag">{ind.tagline}</span>
                    {chosen?.id === ind.id && <span className="iw-check"><Check size={13} /></span>}
                  </button>
                );
              })}
            </div>
            <footer className="iw-foot">
              <button className="link-btn" onClick={() => setDismissed(true)}>Skip for now</button>
              <button className="btn primary" disabled={!chosen} onClick={() => setPhase("confirm")}>
                Continue <ArrowRight size={15} />
              </button>
            </footer>
          </>
        )}

        {/* ── step 2: show exactly what will be created ── */}
        {(phase === "confirm" || phase === "applying") && chosen && (
          <>
            <header className="iw-head">
              <span className="iw-step">Step 2 of 2</span>
              <h2>Here's what {chosen.name.split(" &")[0]} gets</h2>
              <p>{chosen.value}</p>
            </header>

            <div className="iw-preview">
              <section>
                <h4><Bot size={13} /> Specialist agents</h4>
                {chosen.agents.map((a) => (
                  <div key={a.name} className="iw-row">
                    <b>{a.name}</b><span>{a.description}</span>
                  </div>
                ))}
              </section>
              <section>
                <h4><Zap size={13} /> Starter questions</h4>
                {chosen.prompts.map((p) => (
                  <div key={p} className="iw-row"><span className="iw-quote">“{p}”</span></div>
                ))}
              </section>
              <section>
                <h4><Workflow size={13} /> Automation, ready to switch on</h4>
                <div className="iw-row"><b>{chosen.workflow}</b>
                  <span>Runs on every upload — off until you enable it</span></div>
              </section>
            </div>

            {err && <p className="pill bad" style={{ fontSize: 12 }}>{err}</p>}

            <footer className="iw-foot">
              <button className="link-btn" onClick={() => setPhase("pick")} disabled={phase === "applying"}>
                ← Choose a different field
              </button>
              <button className="btn primary" onClick={apply} disabled={phase === "applying"}>
                {phase === "applying"
                  ? <><Loader2 size={15} className="spin" /> Configuring…</>
                  : <>Set up my workspace <ArrowRight size={15} /></>}
              </button>
            </footer>
          </>
        )}

        {/* ── done ── */}
        {phase === "done" && chosen && (
          <div className="iw-done">
            <span className="iw-tick"><Check size={26} /></span>
            <h2>{orgName} is ready</h2>
            <p>
              Configured for {chosen.name}. {result?.agents_created.length ?? 0} specialist agent
              {(result?.agents_created.length ?? 0) === 1 ? "" : "s"} and{" "}
              {result?.workflows_created.length ?? 0} automation are waiting in your workspace.
            </p>
            <div className="iw-done-list">
              {result?.agents_created.map((n) => (
                <span key={n} className="pill good"><Bot size={11} /> {n}</span>
              ))}
              {result?.workflows_created.map((n) => (
                <span key={n} className="pill info"><Workflow size={11} /> {n}</span>
              ))}
            </div>
            <div className="iw-foot" style={{ justifyContent: "center", gap: 10 }}>
              <button className="btn" onClick={() => { setDismissed(true); open("knowledge"); }}>
                Add your documents
              </button>
              <button className="btn primary" onClick={() => { setDismissed(true); open("chat"); }}>
                Ask your first question <ArrowRight size={15} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
