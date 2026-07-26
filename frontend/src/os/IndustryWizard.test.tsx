/* The wizard has one job: make the customer *see* their workspace change.

   The failure mode it exists to prevent is a picker that feels like a settings
   dropdown — pick a field, something invisible happens, and the workspace looks
   identical. So these tests assert on what the reveal actually shows, and that
   every number in it came from the server rather than from the copy. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IndustryWizard from "./IndustryWizard";
import { useOS } from "../store";

vi.mock("../lib/api", () => ({
  apiIndustries: vi.fn(),
  apiSetIndustry: vi.fn(),
}));
import { apiIndustries, apiSetIndustry } from "../lib/api";

const HEALTHCARE = {
  id: "healthcare", name: "Healthcare & Clinics",
  tagline: "Protocols, patient information and compliance",
  icon: "HeartPulse", hue: 350,
  value: "Staff get protocol answers with citations.",
  agents: [
    { name: "Protocol Assistant", description: "Answers from approved protocols" },
    { name: "Compliance Assistant", description: "Checks retention and privacy" },
  ],
  prompts: ["What is our documented protocol for patient intake?",
            "Which of our policies mention data retention periods?"],
  workflow: "Policy change review", analyzer: "auto",
};

const LEGAL = { ...HEALTHCARE, id: "legal", name: "Legal & Professional Services",
                icon: "Scale", hue: 265, agents: [{ name: "Clause Finder", description: "Finds clauses" }] };

const RESULT = {
  industry: "healthcare", name: "Healthcare & Clinics", hue: 350,
  value: "Staff get protocol answers with citations.",
  agents_created: ["Protocol Assistant", "Compliance Assistant"],
  workflows_created: ["Policy change review"],
  documents_created: ["Patient Intake Protocol", "Infection Control Policy",
                      "Consent, Confidentiality and Records Retention"],
  tasks_created: ["Upload your patient intake protocol", "Review who can see personal data",
                  "Invite the practice manager", "Ask about retention", "Check the citations"],
  prompts: HEALTHCARE.prompts, analyzer: "auto",
  compliance_note: "Personal-data access auditing is on by default for this profile.",
};

const ADMIN = { id: "u1", email: "a@clinic.dev", full_name: "Ada Admin", role: "admin", avatar_hue: 200 };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiIndustries).mockResolvedValue([HEALTHCARE, LEGAL] as never);
  vi.mocked(apiSetIndustry).mockResolvedValue(RESULT as never);
  useOS.setState({
    user: ADMIN as never, token: "t", orgName: "Northgate Clinic",
    industry: "", live: true, phase: "desktop", windows: [],
  });
});

/** Walk the wizard the way a person does. */
async function walkToConfirm(field = "healthcare") {
  render(<IndustryWizard />);
  const card = await screen.findByRole("button", { name: new RegExp(field === "legal" ? "Legal" : "Healthcare") });
  fireEvent.click(card);
  fireEvent.click(screen.getByRole("button", { name: /Continue/i }));
}

async function walkToReveal() {
  await walkToConfirm();
  fireEvent.click(screen.getByRole("button", { name: /Set up my workspace/i }));
  return screen.findByTestId("industry-reveal");
}

describe("choosing a field", () => {
  it("is asked only of an admin who has not answered it", async () => {
    useOS.setState({ user: { ...ADMIN, role: "employee" } as never });
    const { container } = render(<IndustryWizard />);
    await waitFor(() => expect(apiIndustries).not.toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("is not asked again once the workspace is configured", async () => {
    useOS.setState({ industry: "healthcare" });
    const { container } = render(<IndustryWizard />);
    await waitFor(() => expect(apiIndustries).not.toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("can be skipped — nobody is trapped in onboarding", async () => {
    render(<IndustryWizard />);
    fireEvent.click(await screen.findByRole("button", { name: /Skip for now/i }));
    await waitFor(() => expect(screen.queryByText(/What does/i)).toBeNull());
  });

  it("will not continue until a field is picked", async () => {
    render(<IndustryWizard />);
    const next = await screen.findByRole("button", { name: /Continue/i });
    expect((next as HTMLButtonElement).disabled).toBe(true);
  });

  it("previews what the field gets before anything is created", async () => {
    await walkToConfirm();
    expect(screen.getByText("Protocol Assistant")).toBeTruthy();
    expect(screen.getByText(/Policy change review/)).toBeTruthy();
    expect(screen.getByText(/patient intake/i)).toBeTruthy();
  });

  it("lets the customer decline the example documents", async () => {
    await walkToConfirm();
    const toggle = screen.getByTestId("with-samples") as HTMLInputElement;
    expect(toggle.checked).toBe(true);   // opt-out: an empty workspace answers nothing
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /Set up my workspace/i }));
    await waitFor(() => expect(apiSetIndustry).toHaveBeenCalledWith("healthcare", false));
  });
});

describe("the reveal", () => {
  it("shows every kind of change the workspace received", async () => {
    const reveal = await walkToReveal();
    const text = reveal.textContent ?? "";
    expect(text).toContain("specialist agent");
    expect(text).toContain("starter document");
    expect(text).toContain("automation");
    expect(text).toContain("task");
  });

  it("counts what the server actually created, not what the copy promises", async () => {
    // The bug this guards against is a reveal that always claims "2 agents,
    // 1 automation" regardless of what happened on the server.
    vi.mocked(apiSetIndustry).mockResolvedValue({
      ...RESULT, agents_created: ["Protocol Assistant"], documents_created: [],
    } as never);
    const reveal = await walkToReveal();
    expect(reveal.textContent).toContain("1 specialist agent,");
    expect(reveal.textContent).not.toContain("starter document");
  });

  it("names the things it created so they can be recognised later", async () => {
    const reveal = await walkToReveal();
    expect(reveal.textContent).toContain("Protocol Assistant");
    expect(reveal.textContent).toContain("Patient Intake Protocol");
    expect(reveal.textContent).toContain("Policy change review");
  });

  it("summarises a long list rather than running off the screen", async () => {
    const reveal = await walkToReveal();
    expect(reveal.textContent).toContain("+1 more");   // 5 tasks, 4 shown
  });

  it("tells the workspace what it has become", async () => {
    await walkToReveal();
    expect(screen.getByText(/Northgate Clinic is a healthcare workspace now/i)).toBeTruthy();
  });

  it("surfaces a compliance note when the field carries one", async () => {
    await walkToReveal();
    expect(screen.getByText(/Personal-data access auditing is on by default/i)).toBeTruthy();
  });

  it("is honest that the starter documents are examples", async () => {
    await walkToReveal();
    expect(screen.getByText(/starter documents are examples/i)).toBeTruthy();
  });

  it("hands over to a first real action", async () => {
    await walkToReveal();
    fireEvent.click(screen.getByRole("button", { name: /Ask your first question/i }));
    await waitFor(() => expect(useOS.getState().windows.some((w) => w.id === "chat")).toBe(true));
  });

  it("keeps the customer on the confirm step if setup fails", async () => {
    vi.mocked(apiSetIndustry).mockRejectedValue(new Error("Workspace not found"));
    await walkToConfirm();
    fireEvent.click(screen.getByRole("button", { name: /Set up my workspace/i }));
    expect(await screen.findByText("Workspace not found")).toBeTruthy();
    expect(screen.queryByTestId("industry-reveal")).toBeNull();
  });
});
