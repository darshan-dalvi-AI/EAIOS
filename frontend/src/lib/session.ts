/**
 * Staying signed in between launches.
 *
 * Until now nothing about the session survived a reload: only the theme was
 * stored, so closing the installed app and reopening it always landed on the
 * login screen. For something presented as an operating system that is the
 * wrong behaviour — you do not log in to your desktop every time you open it.
 *
 * Two rules shape this file.
 *
 * **A stored token is a claim, not proof.** It is never trusted on sight. On
 * launch it is verified against `/api/auth/me`, and the desktop is only shown
 * once the server confirms it. A token that expired, or one issued by a
 * backend that has since been redeployed with a fresh database, fails that
 * check and drops cleanly to sign-in — which is far better than a desktop
 * whose every request 401s.
 *
 * **Demo sessions are never stored.** A demo workspace is throwaway and
 * expires on a timer; restoring one on next launch would resurrect a dead
 * workspace and show its owner an empty, broken desktop. Reopening the app
 * should offer a *fresh* demo, not a stale one.
 */
import type { SessionUser } from "../types";

const KEY = "eaios-session";

export interface StoredSession {
  token: string;
  user: SessionUser;
  orgName: string | null;
  isOwner: boolean;
  industry: string;
}

/** Persist a real (non-demo) session so the next launch can restore it. */
export function saveSession(s: StoredSession): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* private mode, or storage full — staying signed in is a convenience,
       never a requirement, so a failure here is silent by design. */
  }
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing to do */
  }
}

export function readSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as StoredSession;
    // Written by an older build, or hand-edited: anything without the two
    // fields we actually need is not worth trying to repair.
    if (!s?.token || !s?.user?.id) return null;
    return s;
  } catch {
    return null;
  }
}

export interface RestoreResult {
  session: StoredSession;
  /** The server refused because the address is not yet verified. The account
   *  is real, so this goes to the verification gate rather than to sign-in. */
  needsVerification: boolean;
}

/**
 * Verify a stored session against the server.
 *
 * Returns null — and clears the stored session — whenever the token is not
 * currently good for a signed-in desktop. A network failure is treated
 * differently: the backend being briefly unreachable is not evidence that the
 * token is bad, so the session is kept and the caller can retry.
 */
export async function restoreSession(): Promise<RestoreResult | null | "offline"> {
  const stored = readSession();
  if (!stored) return null;

  let res: Response;
  try {
    res = await fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${stored.token}` },
    });
  } catch {
    return "offline";           // keep the session; the server may be waking up
  }

  if (res.status === 403 && res.headers.get("X-Verification-Required") === "1") {
    return { session: stored, needsVerification: true };
  }
  if (!res.ok) {
    clearSession();             // expired, revoked, or a rebuilt database
    return null;
  }

  // Take the server's copy of the profile rather than the stored one: a role
  // change or a rename made since last launch should be reflected immediately.
  try {
    const fresh = (await res.json()) as SessionUser;
    if (fresh?.id) return { session: { ...stored, user: fresh }, needsVerification: false };
  } catch {
    /* fall through to the stored copy */
  }
  return { session: stored, needsVerification: false };
}
