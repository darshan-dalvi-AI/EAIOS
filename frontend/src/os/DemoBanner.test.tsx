/* The demo has to admit what it is.

   The failure this guards against is quiet and expensive: a visitor treats the
   sandbox as a real workspace, uploads real documents, returns tomorrow and
   finds nothing. They learn that the product loses data — the exact opposite of
   what the demo was for. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import DemoBanner from "./DemoBanner";
import { useOS } from "../store";

beforeEach(() => {
  useOS.setState({ demo: false, demoExpiresIn: null, phase: "desktop" });
});

describe("the demo notice", () => {
  it("stays out of a real workspace entirely", () => {
    const { container } = render(<DemoBanner />);
    expect(container.innerHTML).toBe("");
  });

  it("appears in a sandbox and says nothing is saved", () => {
    useOS.setState({ demo: true, demoExpiresIn: 120 });
    render(<DemoBanner />);
    const banner = screen.getByTestId("demo-banner");
    expect(banner.textContent).toMatch(/Demo workspace/i);
    expect(banner.textContent).toMatch(/Nothing is saved/i);
    expect(banner.textContent).toMatch(/reload/i);
  });

  it("is clear that the product itself is real, not a mock-up", () => {
    // A visitor who thinks the answers are canned has learned nothing.
    useOS.setState({ demo: true, demoExpiresIn: 90 });
    render(<DemoBanner />);
    expect(screen.getByTestId("demo-banner").textContent).toMatch(/uploads are indexed/i);
  });

  it("says how long is left", () => {
    useOS.setState({ demo: true, demoExpiresIn: 45 });
    render(<DemoBanner />);
    expect(screen.getByText(/45 min left/)).toBeTruthy();
  });

  it("flags the last few minutes so nobody is surprised mid-demo", () => {
    useOS.setState({ demo: true, demoExpiresIn: 5 });
    render(<DemoBanner />);
    expect(screen.getByTestId("demo-banner").className).toContain("urgent");
  });

  it("handles an expiry that has already passed without going negative", () => {
    useOS.setState({ demo: true, demoExpiresIn: 0 });
    render(<DemoBanner />);
    expect(screen.getByText(/expiring now/i)).toBeTruthy();
  });

  it("can be dismissed — a permanent bar across the screen is its own problem", async () => {
    useOS.setState({ demo: true, demoExpiresIn: 60 });
    render(<DemoBanner />);
    fireEvent.click(screen.getByRole("button", { name: /hide demo notice/i }));
    await waitFor(() => expect(screen.queryByTestId("demo-banner")).toBeNull());
  });

  it("shows nothing about time when the server did not say", () => {
    useOS.setState({ demo: true, demoExpiresIn: null });
    render(<DemoBanner />);
    expect(screen.getByTestId("demo-banner")).toBeTruthy();
    expect(screen.queryByText(/min left/)).toBeNull();
  });
});
