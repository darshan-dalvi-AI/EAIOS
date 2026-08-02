/** Deploy detection — tells a running copy of K-OS that a newer one exists.
 *
 *  The installed app is the reason this is needed. A browser tab gets a fresh
 *  bundle on the next navigation, which happens constantly; an installed PWA
 *  can stay open for days without ever navigating, so it will happily keep
 *  running the build it launched with long after a deploy replaced it.
 *
 *  The previous behaviour was worse than doing nothing: the service worker
 *  called skipWaiting(), grabbed control the instant it finished installing,
 *  and `controllerchange` reloaded the page out from under whoever was using
 *  it. A reload with no warning, mid-chat, looks exactly like a crash.
 *
 *  So now the new worker parks in `waiting`, this module notices, and the app
 *  offers the reload rather than performing it.
 */
import { useOS } from "../store";

/** The installed-but-not-yet-active worker, once one exists. */
let waiting: ServiceWorker | null = null;
let reloading = false;

/** Take the update: hand over to the waiting worker and reload onto it. */
export function applyUpdate(): void {
  if (reloading) return;
  reloading = true;

  if (!waiting) {
    // No waiting worker (or it went away between prompt and click) — a plain
    // reload still fetches the new shell, so the button is never a dead end.
    location.reload();
    return;
  }

  waiting.postMessage({ type: "SKIP_WAITING" });
  // `controllerchange` below does the reload. This is the backstop for the
  // case where the worker never activates: the person clicked Reload and must
  // get a reload, not a button that quietly did nothing.
  setTimeout(() => location.reload(), 2500);
}

/** Is the waiting worker actually a different build from the one running here?
 *
 *  A waiting worker is not by itself proof that this page is stale. The app
 *  shell is fetched network-first, so the first load after a deploy already
 *  runs the new bundle — while the new *worker* is still queued behind the old
 *  one. That combination would otherwise announce "a new version is ready" to
 *  someone looking at the new version, which teaches people to ignore the
 *  prompt, and an ignored prompt is worse than none.
 *
 *  Both files are stamped by the same build, so comparing them answers it.
 *  On any doubt this returns true: a spurious prompt costs one reload, a
 *  suppressed one leaves the app stale indefinitely.
 */
async function isGenuinelyNewer(): Promise<boolean> {
  try {
    const res = await fetch("/sw.js", { cache: "no-store" });
    if (!res.ok) return true;
    const stamped = /const BUILD = "([^"]+)"/.exec(await res.text());
    if (!stamped) return true;
    return stamped[1] !== __BUILD_ID__;
  } catch {
    return true;
  }
}

export function initUpdates(): void {
  if (!import.meta.env.PROD) return;
  if (!("serviceWorker" in navigator)) return;
  if (!location.protocol.startsWith("http")) return;   // file:// single-file demo

  // Fires when the waiting worker takes over — i.e. after applyUpdate(), or
  // when another tab of the same app applied it. Both want this tab reloaded
  // onto the new bundle; running half-old, half-new chunks is what produced
  // the minified "x is not a function" crashes.
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (reloading) { location.reload(); return; }
    reloading = true;
    location.reload();
  });

  void navigator.serviceWorker.register("/sw.js").then((reg) => {
    const announce = async (sw: ServiceWorker | null) => {
      if (!sw || sw.state !== "installed") return;
      // A freshly installed worker with no controller is the FIRST install,
      // not an update. Announcing that would show "update available" to
      // someone who just opened the app for the first time.
      if (!navigator.serviceWorker.controller) return;
      if (!(await isGenuinelyNewer())) return;
      waiting = sw;
      useOS.getState().setUpdateReady(true);
    };

    void announce(reg.waiting);            // finished installing before this page loaded
    reg.addEventListener("updatefound", () => {
      const sw = reg.installing;
      sw?.addEventListener("statechange", () => void announce(sw));
    });

    // Browsers check for a new worker on navigation. An installed app may not
    // navigate for days, so ask explicitly: on a timer, and whenever the
    // window comes back to the foreground — which is when someone is about to
    // look at it, and so the moment the answer matters.
    const check = () => { if (navigator.onLine) void reg.update().catch(() => {}); };
    setInterval(check, 15 * 60 * 1000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
    window.addEventListener("online", check);
  }).catch(() => {/* non-fatal: the app works fine without a worker */});
}
