/* Hitting a limit is the most attentive a customer will ever be.

   These tests are about what they see at that moment: whether they are told
   what they hit, how close they were, what the next plan changes, and — if
   they are not the person who can pay — what to do instead. A 402 that reaches
   the user as a red toast wastes the only moment they were definitely going to
   read carefully. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import UpgradeDialog, { PlanPanel } from "./UpgradeDialog";
import { PLAN_LIMIT_EVENT } from "../lib/api";
import { useOS } from "../store";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, apiBilling: vi.fn(), apiChangePlan: vi.fn() };
});
import { apiBilling, apiChangePlan } from "../lib/api";

const BILLING = {
  plan: { id: "free", name: "Free", price_month: 0, blurb: "Prove it works.", highlights: [] },
  usage: [
    { key: "documents", label: "documents", used: 25, limit: 25, unlimited: false },
    { key: "seats", label: "people", used: 5, limit: 5, unlimited: false },
    { key: "custom_agents", label: "custom agents", used: 2, limit: 2, unlimited: false },
    { key: "automations", label: "running automations", used: 0, limit: 0, unlimited: false },
  ],
  features: { connectors: false, video: false, audit_export: false, ai_daily_tokens: 50000 },
  plans: [
    { id: "free", name: "Free", price_month: 0, blurb: "Prove it works.", highlights: ["25 documents"],
      current: true, documents: 25, custom_agents: 2, seats: 5, automations: 0,
      connectors: false, video: false, audit_export: false, ai_daily_tokens: 50000 },
    { id: "pro", name: "Pro", price_month: 49, blurb: "For a team.", highlights: ["1,000 documents"],
      current: false, documents: 1000, custom_agents: -1, seats: 15, automations: 10,
      connectors: true, video: true, audit_export: false, ai_daily_tokens: 500000 },
    { id: "business", name: "Business", price_month: 149, blurb: "Audited.", highlights: ["Unlimited"],
      current: false, documents: -1, custom_agents: -1, seats: -1, automations: -1,
      connectors: true, video: true, audit_export: true, ai_daily_tokens: 2000000 },
  ],
};

const ADMIN = { id: "u1", email: "a@co.dev", full_name: "Ada Admin", role: "admin", avatar_hue: 200 };
const STAFF = { ...ADMIN, id: "u2", role: "employee", full_name: "Sam Staff" };

function hitLimit(over: Record<string, unknown> = {}) {
  window.dispatchEvent(new CustomEvent(PLAN_LIMIT_EVENT, {
    detail: {
      limit: "documents", used: 25, plan: "free", plan_name: "Free",
      upgrade_to: "pro", upgrade_name: "Pro", upgrade_allows: "1,000 documents",
      detail: "You've used all 25 documents on the Free plan.",
      ...over,
    },
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiBilling).mockResolvedValue(BILLING as never);
  useOS.setState({ user: ADMIN as never, token: "t", orgName: "Acme", phase: "desktop" });
});

describe("when a plan limit stops someone", () => {
  it("stays out of the way until a limit is actually hit", () => {
    const { container } = render(<UpgradeDialog />);
    expect(container.innerHTML).toBe("");
  });

  it("opens on a 402 raised anywhere in the app", async () => {
    render(<UpgradeDialog />);
    hitLimit();
    expect(await screen.findByTestId("upgrade-dialog")).toBeTruthy();
  });

  it("says what was hit in the words of what they were doing", async () => {
    render(<UpgradeDialog />);
    hitLimit();
    await screen.findByTestId("upgrade-dialog");
    expect(screen.getByText("You've used all 25 documents on the Free plan.")).toBeTruthy();
  });

  it("shows how close they were, not just that they failed", async () => {
    render(<UpgradeDialog />);
    hitLimit();
    const meter = await screen.findByTestId("limit-meter");
    expect(meter.textContent).toContain("25 of 25");
  });

  it("marks the plan that lifts this particular limit", async () => {
    render(<UpgradeDialog />);
    hitLimit();
    await screen.findByTestId("upgrade-dialog");
    expect(screen.getByText("Lifts this limit")).toBeTruthy();
    // and never offers the plan they are already on
    expect(screen.queryByTestId("choose-free")).toBeNull();
  });

  it("switches plan and closes when they accept", async () => {
    vi.mocked(apiChangePlan).mockResolvedValue({
      ...BILLING, previous: "free",
      plan: { id: "pro", name: "Pro", price_month: 49, blurb: "", highlights: [] },
    } as never);
    render(<UpgradeDialog />);
    hitLimit();
    fireEvent.click(await screen.findByTestId("choose-pro"));

    await waitFor(() => expect(apiChangePlan).toHaveBeenCalledWith("pro"));
    await waitFor(() => expect(screen.queryByTestId("upgrade-dialog")).toBeNull());
  });

  it("tells someone who cannot pay what to do instead of dead-ending them", async () => {
    useOS.setState({ user: STAFF as never });
    render(<UpgradeDialog />);
    hitLimit();
    await screen.findByTestId("upgrade-dialog");
    expect(screen.getByText(/Ask an admin/i)).toBeTruthy();
    expect((screen.getByTestId("choose-pro") as HTMLButtonElement).disabled).toBe(true);
  });

  it("promises that downgrading will not delete their work", async () => {
    // The fear that stops people trying a paid plan is losing data if they stop
    // paying. Saying so at the decision point is the whole job of this line.
    render(<UpgradeDialog />);
    hitLimit();
    await screen.findByTestId("upgrade-dialog");
    expect(screen.getByText(/Nothing you already have is removed/i)).toBeTruthy();
  });

  it("can be dismissed — a limit must never trap the workspace", async () => {
    render(<UpgradeDialog />);
    hitLimit();
    await screen.findByTestId("upgrade-dialog");
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByTestId("upgrade-dialog")).toBeNull());
  });

  it("adapts its headline to the limit that was hit", async () => {
    render(<UpgradeDialog />);
    hitLimit({ limit: "seats", detail: "You've used all 5 people on the Free plan." });
    await screen.findByTestId("upgrade-dialog");
    expect(screen.getByText("Your workspace is full")).toBeTruthy();
  });
});

describe("the plan panel in settings", () => {
  it("shows usage against every limit before anyone hits one", async () => {
    render(<PlanPanel />);
    await screen.findByTestId("plan-panel");
    expect(screen.getByText("25 / 25")).toBeTruthy();
    expect(screen.getByText("5 / 5")).toBeTruthy();
  });

  it("marks the current plan and offers no switch to it", async () => {
    render(<PlanPanel />);
    await screen.findByTestId("plan-panel");
    expect(screen.getByText("Your plan")).toBeTruthy();
    expect((screen.getByTestId("plan-free") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("plan-pro") as HTMLButtonElement).disabled).toBe(false);
  });

  it("reads unlimited as a word, not as minus one", async () => {
    render(<PlanPanel />);
    await screen.findByTestId("plan-panel");
    expect(screen.queryByText(/-1/)).toBeNull();
    expect(screen.getAllByText(/Unlimited/i).length).toBeGreaterThan(0);
  });

  it("does not let a non-admin change the plan", async () => {
    useOS.setState({ user: STAFF as never });
    render(<PlanPanel />);
    await screen.findByTestId("plan-panel");
    expect((screen.getByTestId("plan-pro") as HTMLButtonElement).disabled).toBe(true);
  });
});
