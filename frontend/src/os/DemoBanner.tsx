/* A standing reminder that this workspace is temporary.

   The sandbox only works as an honest demo if the person knows what it is.
   Without this, someone uploads real documents, comes back tomorrow and finds
   an empty workspace — which teaches them the product loses data, the exact
   opposite of what the demo is for.

   So it says three things and stays out of the way: this is a demo, nothing is
   saved, and here is how long you have. */
import { Clock, FlaskConical, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useOS } from "../store";

export default function DemoBanner() {
  const demo = useOS((s) => s.demo);
  const expiresIn = useOS((s) => s.demoExpiresIn);
  const [dismissed, setDismissed] = useState(false);
  const [left, setLeft] = useState<number | null>(expiresIn ?? null);

  useEffect(() => { setLeft(expiresIn ?? null); }, [expiresIn]);

  // Count down locally rather than polling the server for something the server
  // already told us once.
  useEffect(() => {
    if (!demo || left == null) return;
    const t = setInterval(() => setLeft((m) => (m == null ? m : Math.max(0, m - 1))), 60_000);
    return () => clearInterval(t);
  }, [demo, left]);

  if (!demo || dismissed) return null;

  const urgent = left != null && left <= 10;

  return (
    <div className={`demo-banner${urgent ? " urgent" : ""}`} role="status" data-testid="demo-banner">
      <span className="demo-ico"><FlaskConical size={13} /></span>
      <b>Demo workspace</b>
      <span className="demo-copy">
        Everything here is real — uploads are indexed, answers are cited. Nothing
        is saved: reload the page and you start fresh.
      </span>
      {left != null && (
        <span className="demo-time" title="This workspace is deleted when the time runs out">
          <Clock size={11} /> {left > 0 ? `${left} min left` : "expiring now"}
        </span>
      )}
      <button className="demo-x" onClick={() => setDismissed(true)} aria-label="Hide demo notice">
        <X size={13} />
      </button>
    </div>
  );
}
