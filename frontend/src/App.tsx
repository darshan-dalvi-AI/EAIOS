import BootScreen from "./os/BootScreen";
import Desktop from "./os/Desktop";
import LandingPage from "./os/LandingPage";
import LoginScreen from "./os/LoginScreen";
import VerifyEmail from "./os/VerifyEmail";
import { useOS } from "./store";

export default function App() {
  const phase = useOS((s) => s.phase);
  // A workspace exists but stays unusable until its owner proves the address.
  // The server enforces the same rule, so this is the courtesy, not the lock.
  const emailVerified = useOS((s) => s.emailVerified);

  return (
    <>
      <div className="desktop" aria-hidden>
        <div className="aurora-drift" />
      </div>
      {phase === "landing" && <LandingPage />}
      {phase === "boot" && <BootScreen />}
      {phase === "login" && <LoginScreen />}
      {phase === "desktop" && (emailVerified ? <Desktop /> : <VerifyEmail />)}
    </>
  );
}
