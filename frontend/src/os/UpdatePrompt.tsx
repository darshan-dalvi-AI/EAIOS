/** "A new version is ready" — shown when a deploy lands while the app is open.
 *
 *  Deliberately a prompt and not an automatic reload. K-OS holds unsaved state
 *  the person cares about: a half-typed question, an unsaved file in the Code
 *  app, an agent run in flight. Reloading without asking throws all of that
 *  away and is indistinguishable from a crash. So this waits.
 *
 *  Dismiss is honest about what it does: the update stays downloaded and
 *  applies at the next launch either way, so "Later" costs nothing.
 */
import { Download, X } from "lucide-react";
import { applyUpdate } from "../lib/updates";
import { useOS } from "../store";
import Mark from "./Mark";

export default function UpdatePrompt() {
  const updateReady = useOS((s) => s.updateReady);
  const setUpdateReady = useOS((s) => s.setUpdateReady);
  if (!updateReady) return null;

  return (
    <div className="kos-update" role="status" aria-live="polite">
      <span className="kos-update-ico"><Mark size={18} /></span>
      <div className="kos-update-copy">
        <b>A new version of K-OS is ready</b>
        <span>
          Reload to switch to it — or keep working and it applies at the next launch.
          {" "}You are on build <code>{__BUILD_ID__}</code>.
        </span>
      </div>
      <button className="btn primary sm" onClick={applyUpdate}>
        <Download size={13} /> Reload
      </button>
      <button
        className="kos-update-x"
        onClick={() => setUpdateReady(false)}
        aria-label="Dismiss until next launch"
        title="Later"
      >
        <X size={14} />
      </button>
    </div>
  );
}
