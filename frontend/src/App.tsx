import { useEffect } from "react";
import { restoreSession } from "./lib/session";
import BootScreen from "./os/BootScreen";
import Desktop from "./os/Desktop";
import LandingPage from "./os/LandingPage";
import LoginScreen from "./os/LoginScreen";
import UpdatePrompt from "./os/UpdatePrompt";
import VerifyEmail from "./os/VerifyEmail";
import { isInstalledApp, useOS } from "./store";

export default function App() {
  const phase = useOS((s) => s.phase);
  // A workspace exists but stays unusable until its owner proves the address.
  // The server enforces the same rule, so this is the courtesy, not the lock.
  const emailVerified = useOS((s) => s.emailVerified);

  /* Signed in last time? Verify that token with the server and go straight to
     the desktop. The check is deliberately not skipped: a token can expire, be
     revoked, or belong to a database that has since been rebuilt, and showing
     a desktop whose every request then fails is worse than asking for a
     password. Runs once, only when the app started in "restoring". */
  useEffect(() => {
    if (phase !== "restoring") return;
    let cancelled = false;

    void (async () => {
      const result = await restoreSession();
      if (cancelled) return;
      const os = useOS.getState();

      if (result === "offline") {
        // The backend is unreachable — on a free host it may simply be waking
        // up. That is not evidence the token is bad, so the session is kept
        // and the person lands on sign-in rather than being silently logged
        // out of a workspace they still belong to.
        os.setPhase(isInstalledApp() ? "login" : "landing");
        return;
      }
      if (!result) {
        os.setPhase(isInstalledApp() ? "login" : "landing");
        return;
      }

      const { session, needsVerification } = result;
      os.setLive(true);
      os.login(session.user, session.token, session.orgName, session.isOwner,
               session.industry, !needsVerification);
    })();

    return () => { cancelled = true; };
  }, [phase]);

  return (
    <>
      <div className="desktop" aria-hidden>
        <div className="aurora-drift" />
      </div>
      {phase === "landing" && <LandingPage />}
      {/* "restoring" shows the same boot sequence — it is honestly what is
          happening, and it avoids a flash of the sign-in screen before the
          desktop appears. BootScreen only auto-advances while the phase is
          still "boot", so it cannot race this. */}
      {(phase === "boot" || phase === "restoring") && <BootScreen />}
      {phase === "login" && <LoginScreen />}
      {phase === "desktop" && (emailVerified ? <Desktop /> : <VerifyEmail />)}
      {/* Outside the phase switch on purpose: a deploy can land at any point,
          including while someone is sitting on the landing page. */}
      <UpdatePrompt />
    </>
  );
}
