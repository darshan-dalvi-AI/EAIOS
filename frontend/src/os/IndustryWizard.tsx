/* Industry personalisation — the first thing a new company sees.
   An empty AI workspace asks the customer to imagine what it could do for
   their business, and most never get there. This asks one question instead,
   then configures the workspace in front of them: specialist agents written
   for their field, the questions their staff actually ask, and an intake
   automation. Shown once per workspace, to the admin only. */
import {
  ArrowRight, Bot, Briefcase, Building2, Check, Factory, FileText, GraduationCap,
  HeartPulse, Landmark, ListChecks, Loader2, Scale, ShieldCheck, ShoppingBag,
  Sparkles, Users, Workflow, Zap,
} from "lucide-react";
import { useEffect, useState } from "react";
import { apiIndustries, apiSetIndustry, type Industry, type IndustryResult } from "../lib/api";
import { useOS } from "../store";

const ICONS: Record<string, typeof Bot> = {
  Briefcase, HeartPulse, Scale, Landmark, Users, Factory,
  GraduationCap, Building2, ShoppingBag, Sparkles,
};

type Phase = "pick" | "confirm" | "applying" | "done";

/** The reveal is the whole point of the wizard: the customer has to *see* the
 *  workspace change, not be told it did. Each row reads a different part of
 *  the server's answer, so it can only show what genuinely happened. */
const REVEAL: {
  key: string; Icon: typeof Bot;
  label: (n: number) => string;
  pick: (r: IndustryResult | null) => string[];
}[] = [
  { key: "agents", Icon: Bot,
    label: (n) => `specialist agent${n === 1 ? "" : "s"}, trained on your field`,
    pick: (r) => r?.agents_created ?? [] },
  { key: "docs", Icon: FileText,
    label: (n) => `starter document${n === 1 ? "" : "s"}, indexed and searchable`,
    pick: (r) => r?.documents_created ?? [] },
  { key: "flows", Icon: Workflow,
    label: (n) => `automation${n === 1 ? "" : "s"}, ready to switch on`,
    pick: (r) => r?.workflows_created ?? [] },
  { key: "tasks", Icon: ListChecks,
    label: (n) => `task${n === 1 ? "" : "s"} on your board for this week`,
    pick: (r) => r?.tasks_created ?? [] },
];

export default function IndustryWizard() {
  const { user, orgName, industry, setIndustry, live, open } = useOS();
  const [list, setList] = useState<Industry[] | null>(null);
  const [chosen, setChosen] = useState<Industry | null>(null);
  const [phase, setPhase] = useState<Phase>("pick");
  const [result, setResult] = useState<IndustryResult | null>(null);
  // Opt-out, not opt-in: a workspace that answers nothing on day one reads
  // as a broken product rather than an empty one.
  const [withSamples, setWithSamples] = useState(true);
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
      const r: IndustryResult = live
        ? await apiSetIndustry(chosen.id, withSamples)
        : {
            industry: chosen.id, name: chosen.name, hue: chosen.hue, value: chosen.value,
            agents_created: chosen.agents.map((a) => a.name),
            workflows_created: [chosen.workflow],
            documents_created: [], tasks_created: [],
            prompts: chosen.prompts, analyzer: chosen.analyzer, compliance_note: "",
          };
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
                K-OS configures itself for your field — specialist AI agents, the questions your
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
              <section>
                <h4><FileText size={13} /> Something to ask questions about</h4>
                <label className="iw-check-row">
                  <input type="checkbox" checked={withSamples} data-testid="with-samples"
                         onChange={(e) => setWithSamples(e.target.checked)} />
                  <span>
                    <b>Add example {chosen.name.split(" &")[0].toLowerCase()} documents</b>
                    <span>So the questions above answer immediately. Clearly labelled,
                      and removable in one click.</span>
                  </span>
                </label>
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

        {/* ── the reveal: what actually changed, item by item ── */}
        {phase === "done" && chosen && (
          <div className="iw-done" style={{ "--hue": chosen.hue } as React.CSSProperties}>
            <span className="iw-tick"><Check size={26} /></span>
            <h2>{orgName} is a {chosen.name.split(" &")[0].toLowerCase()} workspace now</h2>
            <p>{chosen.value}</p>

            <div className="iw-reveal" data-testid="industry-reveal">
              {REVEAL.map((row, i) => {
                const items = row.pick(result);
                if (!items.length) return null;
                return (
                  <section key={row.key} className="iw-rev" style={{ animationDelay: `${i * 110}ms` }}>
                    <header>
                      <span className="iw-rev-ico"><row.Icon size={14} /></span>
                      <b>{items.length}</b> {row.label(items.length)}
                    </header>
                    <ul>
                      {items.slice(0, 4).map((name) => <li key={name}>{name}</li>)}
                      {items.length > 4 && <li className="faint">+{items.length - 4} more</li>}
                    </ul>
                  </section>
                );
              })}
            </div>

            {result?.compliance_note && (
              <p className="iw-note"><ShieldCheck size={13} /> {result.compliance_note}</p>
            )}

            {!!result?.documents_created.length && (
              <p className="iw-note faint">
                The starter documents are examples so you can try a question straight away —
                remove them any time from Knowledge.
              </p>
            )}

            <div className="iw-foot" style={{ justifyContent: "center", gap: 10 }}>
              <button className="btn" onClick={() => { setDismissed(true); open("knowledge"); }}>
                Add your own documents
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
