/* Google Identity Services loader.

   Loaded on demand rather than on every page view: most visitors never sign
   in with Google, and the script is a third-party request the landing page
   shouldn't make on their behalf. The returned ID token is only meaningful
   after the server verifies it (see services/google_auth.py) — this file
   just obtains it. */

interface GisTokenClient { requestIdToken(): Promise<string> }

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize(cfg: Record<string, unknown>): void;
          prompt(cb?: (n: unknown) => void): void;
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

export async function loadGis(clientId: string): Promise<GisTokenClient> {
  if (!clientId) throw new Error("Google sign-in isn't configured on this deployment.");
  await loadScript();
  const gid = window.google?.accounts?.id;
  if (!gid) throw new Error("Couldn't load Google sign-in.");

  return {
    requestIdToken(): Promise<string> {
      return new Promise((resolve, reject) => {
        let settled = false;
        gid.initialize({
          client_id: clientId,
          callback: (res: { credential?: string }) => {
            settled = true;
            res?.credential ? resolve(res.credential)
                            : reject(new Error("Google didn't return a sign-in token."));
          },
          cancel_on_tap_outside: false,
          use_fedcm_for_prompt: true,
        });
        gid.prompt(() => {
          // The prompt can be dismissed or suppressed; don't hang forever.
          setTimeout(() => {
            if (!settled) reject(new Error("The Google popup was closed before finishing."));
          }, 500);
        });
      });
    },
  };
}
