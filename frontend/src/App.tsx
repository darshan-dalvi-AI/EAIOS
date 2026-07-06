import BootScreen from "./os/BootScreen";
import Desktop from "./os/Desktop";
import LandingPage from "./os/LandingPage";
import LoginScreen from "./os/LoginScreen";
import { useOS } from "./store";

export default function App() {
  const phase = useOS((s) => s.phase);

  return (
    <>
      <div className="desktop" aria-hidden>
        <div className="aurora-drift" />
      </div>
      {phase === "landing" && <LandingPage />}
      {phase === "boot" && <BootScreen />}
      {phase === "login" && <LoginScreen />}
      {phase === "desktop" && <Desktop />}
    </>
  );
}
