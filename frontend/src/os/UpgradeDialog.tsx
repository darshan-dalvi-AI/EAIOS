/* The moment someone hits a plan limit.

   A refusal is the most attentive a customer will ever be: they were mid-task,
   they wanted the thing, and they have just been stopped. Showing "Error 402"
   wastes that. This names what they hit, what they have used, and what the
   next plan would give them — in the words of the thing they were doing.

   It is opened from anywhere by dispatching `eaios:plan-limit` with the
   ApiError's planBlock, so no screen needs to know how upgrading works. */
import { ArrowRight, Check, Loader2, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  apiBilling, apiChangePlan, PLAN_LIMIT_EVENT,
  type Billing, type PlanBlock, type PlanRow,
} from "../lib/api";
import { useOS } from "../store";

function fmt(n: number) {
  return n === -1 ? "Unlimited" : n.toLocaleString();
}

export default function UpgradeDialog() {
  const { user, pushFeed } = useOS();
  const [block, setBlock] = useState<PlanBlock | null>(null);
  const [billing, setBilling] = useState<Billing | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    const onLimit = (e: Event) => {
      setBlock((e as CustomEvent<PlanBlock>).detail);
      setErr("");
      apiBilling().then(setBilling).catch(() => setBilling(null));
    };
    window.addEventListener(PLAN_LIMIT_EVENT, onLimit);
    return () => window.removeEventListener(PLAN_LIMIT_EVENT, onLimit);
  }, []);

  useEffect(() => {
    if (!block) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setBlock(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [block]);

  if (!block) return null;

  const canChange = user?.role === "admin";
  const offered = billing?.plans.filter((p) => !p.current) ?? [];
  const hit = billing?.usage.find((u) => u.key === block.limit);

  async function choose(plan: PlanRow) {
    setBusy(plan.id);
    setErr("");
    try {
      const next = await apiChangePlan(plan.id);
      setBilling(next);
      pushFeed({ agent: "system", kind: "system",
                 text: `Workspace moved to the ${next.plan.name} plan.` });
      setBlock(null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not change the plan.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="up-backdrop" role="dialog" aria-modal="true" aria-label="Plan limit reached"
         onMouseDown={(e) => { if (e.target === e.currentTarget) setBlock(null); }}>
      <div className="up" data-testid="upgrade-dialog">
        <button className="up-x" onClick={() => setBlock(null)} aria-label="Close">
          <X size={15} />
        </button>

        <header className="up-head">
          <span className="up-badge"><Sparkles size={13} /> {block.plan_name} plan</span>
          <h2>{block.limit === "seats" ? "Your workspace is full"
             : block.limit === "automations" ? "Automations need a paid plan"
             : block.limit === "connectors" ? "Connectors need a paid plan"
             : "You've reached a limit"}</h2>
          <p>{(block as unknown as { detail?: string }).detail || "This action isn't included in your current plan."}</p>
        </header>

        {hit && !hit.unlimited && (
          <div className="up-meter" data-testid="limit-meter">
            <div className="up-meter-top">
              <span>{hit.label}</span>
              <b>{hit.used.toLocaleString()} of {hit.limit.toLocaleString()}</b>
            </div>
            <div className="up-bar">
              <i style={{ width: `${Math.min(100, (hit.used / Math.max(1, hit.limit)) * 100)}%` }} />
            </div>
          </div>
        )}

        {offered.length > 0 && (
          <div className="up-plans">
            {offered.map((p) => (
              <section key={p.id} className={`up-plan ${p.id === block.upgrade_to ? "reco" : ""}`}>
                {p.id === block.upgrade_to && <span className="up-reco">Lifts this limit</span>}
                <h3>{p.name}</h3>
                <div className="up-price">
                  {p.price_month === 0 ? "Free" : <>${p.price_month}<span>/month</span></>}
                </div>
                <p className="up-blurb">{p.blurb}</p>
                <ul>
                  {p.highlights.map((hl) => (
                    <li key={hl}><Check size={12} /> {hl}</li>
                  ))}
                </ul>
                <button className={`btn ${p.id === block.upgrade_to ? "primary" : ""}`}
                        style={{ justifyContent: "center", width: "100%" }}
                        disabled={!canChange || !!busy}
                        data-testid={`choose-${p.id}`}
                        onClick={() => choose(p)}>
                  {busy === p.id ? <><Loader2 size={14} className="spin" /> Switching…</>
                                 : <>Choose {p.name} <ArrowRight size={14} /></>}
                </button>
              </section>
            ))}
          </div>
        )}

        {err && <p className="pill bad" style={{ fontSize: 12 }}>{err}</p>}

        {!canChange && (
          <p className="up-foot">
            Ask an admin in your workspace to change the plan — you can keep working on
            everything inside the {block.plan_name} plan meanwhile.
          </p>
        )}
        {canChange && (
          <p className="up-foot faint">
            Nothing you already have is removed if you move down a plan later —
            you simply cannot add more until you are back under the limit.
          </p>
        )}
      </div>
    </div>
  );
}

/** Plan comparison with live usage, for Settings. Same data, no urgency. */
export function PlanPanel() {
  const { user } = useOS();
  const [billing, setBilling] = useState<Billing | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => { apiBilling().then(setBilling).catch(() => setBilling(null)); }, []);
  if (!billing) return <p className="faint" style={{ fontSize: 12 }}>Loading your plan…</p>;

  async function choose(id: string) {
    setBusy(id);
    try { setBilling(await apiChangePlan(id)); } finally { setBusy(""); }
  }

  return (
    <div className="plan-panel" data-testid="plan-panel">
      <div className="up-meters">
        {billing.usage.map((u) => {
          const pct = u.unlimited ? 0 : Math.min(100, (u.used / Math.max(1, u.limit)) * 100);
          return (
            <div key={u.key} className="up-meter">
              <div className="up-meter-top">
                <span>{u.label}</span>
                <b>{u.used.toLocaleString()}{u.unlimited ? "" : ` / ${u.limit.toLocaleString()}`}</b>
              </div>
              <div className="up-bar">
                <i className={pct >= 90 ? "hot" : pct >= 70 ? "warm" : ""}
                   style={{ width: u.unlimited ? "8%" : `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="up-plans">
        {billing.plans.map((p) => (
          <section key={p.id} className={`up-plan ${p.current ? "reco" : ""}`}>
            {p.current && <span className="up-reco">Your plan</span>}
            <h3>{p.name}</h3>
            <div className="up-price">
              {p.price_month === 0 ? "Free" : <>${p.price_month}<span>/month</span></>}
            </div>
            <p className="up-blurb">{p.blurb}</p>
            <ul>
              <li><Check size={12} /> {fmt(p.documents)} documents</li>
              <li><Check size={12} /> {fmt(p.seats)} people</li>
              <li><Check size={12} /> {fmt(p.custom_agents)} custom agents</li>
              <li><Check size={12} /> {p.automations === 0 ? "No running automations" : `${fmt(p.automations)} automations`}</li>
              {p.connectors && <li><Check size={12} /> Drive, Gmail and web connectors</li>}
              {p.audit_export && <li><Check size={12} /> Audit-log export</li>}
            </ul>
            <button className={`btn ${p.current ? "" : "primary"}`}
                    style={{ justifyContent: "center", width: "100%" }}
                    disabled={p.current || user?.role !== "admin" || !!busy}
                    data-testid={`plan-${p.id}`}
                    onClick={() => choose(p.id)}>
              {busy === p.id ? "Switching…" : p.current ? "Current plan" : `Switch to ${p.name}`}
            </button>
          </section>
        ))}
      </div>
      <p className="up-foot faint">
        This deployment has no payment processor connected — an admin sets the plan directly,
        and the limits above are enforced by the server either way.
      </p>
    </div>
  );
}
