/* PWA install support — lets users install EAIOS as a standalone app on
   Windows, macOS and Android straight from the browser (no store needed).
   Chromium fires `beforeinstallprompt`; we defer it and trigger it from our
   own "Download app" button. iOS Safari has no prompt API, so we show manual
   "Add to Home Screen" instructions instead. */

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((f) => f());

/** Register global listeners as early as possible (called from main.tsx). */
export function initPwa(): void {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e as BeforeInstallPromptEvent;
    notify();
  });
  window.addEventListener("appinstalled", () => { deferred = null; notify(); });
}

export function canInstall(): boolean {
  return deferred !== null;
}

export function isStandalone(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function isIOS(): boolean {
  const ua = navigator.userAgent || "";
  return /iphone|ipad|ipod/i.test(ua) && !(window as unknown as { MSStream?: unknown }).MSStream;
}

/** Trigger the native install prompt. Returns "unavailable" if the browser
    didn't offer one (iOS, Firefox, Safari, or already-installed). */
export async function promptInstall(): Promise<"accepted" | "dismissed" | "unavailable"> {
  if (!deferred) return "unavailable";
  await deferred.prompt();
  const { outcome } = await deferred.userChoice;
  deferred = null;
  notify();
  return outcome;
}

export function onPwaChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
