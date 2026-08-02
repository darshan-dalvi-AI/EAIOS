/* Google Identity Services loader.

   Loaded on demand rather than on every page view: most visitors never sign
   in with Google, and the script is a third-party request the landing page
   shouldn't make on their behalf. The returned ID token is only meaningful
   after the server verifies it (see services/google_auth.py) — this file
   just obtains it.

   ── Why a rendered button and not One Tap ────────────────────────────────
   This used to call `google.accounts.id.prompt()`, which is One Tap. Two
   things made that fail on a phone, and both surfaced as the same unhelpful
   message: "The Google window was closed before finishing."

   1. One Tap is suppressed outright in many mobile contexts — an installed
      PWA, a browser restricting third-party cookies, a prompt dismissed once
      already. It never displays, so it can never complete.
   2. The moment-notification callback fires for EVERY moment, including
      "displayed" and "skipped". The old code treated any notification as a
      dismissal and rejected 500 ms later — so even when One Tap did appear,
      it raced the person answering it and usually won.

   `renderButton` is the flow Google supports everywhere: it draws a real
   button in an iframe it controls, handles the popup or redirect itself
   according to what the platform allows, and delivers the credential to the
   same callback. It is the documented path for mobile and standalone PWAs. */

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(cfg: Record<string, unknown>): void;
          renderButton(parent: HTMLElement, opts: Record<string, unknown>): void;
          prompt(cb?: (n: unknown) => void): void;
          cancel(): void;
        };
      };
    };
  }
}

let scriptPromise: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = "https://accounts.google.com/gsi/client";
    el.async = true;
    el.defer = true;
    el.onload = () => resolve();
    el.onerror = () => { scriptPromise = null; reject(new Error("Couldn't load Google sign-in.")); };
    document.head.appendChild(el);
  });
  return scriptPromise;
}

/** Draw Google's own sign-in button into `parent`.
 *
 *  `onCredential` is invoked from inside Google's iframe, so it must not rely
 *  on React state captured at mount time — the caller reads what it needs
 *  from a ref.
 */
export async function mountGoogleButton(
  clientId: string,
  parent: HTMLElement,
  onCredential: (idToken: string) => void,
  onError: (message: string) => void,
): Promise<void> {
  if (!clientId) throw new Error("Google sign-in isn't configured on this deployment.");
  await loadScript();
  const gid = window.google?.accounts?.id;
  if (!gid) throw new Error("Couldn't load Google sign-in.");

  gid.initialize({
    client_id: clientId,
    callback: (res: { credential?: string }) => {
      if (res?.credential) onCredential(res.credential);
      else onError("Google didn't return a sign-in token. Try again.");
    },
    // FedCM governs the One Tap prompt only; the rendered button is
    // unaffected either way, so leaving it on future-proofs the flow at no
    // cost now that the prompt is no longer the path we depend on.
    use_fedcm_for_prompt: true,
    cancel_on_tap_outside: false,
  });

  parent.replaceChildren();
  gid.renderButton(parent, {
    type: "standard",
    theme: "filled_black",
    size: "large",
    text: "continue_with",
    shape: "pill",
    logo_alignment: "left",
    // Google requires an explicit pixel width and only honours 200–400, so
    // the card width is measured and clamped rather than passed straight in.
    width: Math.max(200, Math.min(400,
      Math.round(parent.getBoundingClientRect().width) || 320)),
  });
}
