/* Removing someone from the workspace, from the admin's side.

   The server refuses the dangerous cases, but an interface that lets you click
   a button and then explains why it could never have worked is a worse
   interface than one that shows you the rule up front. So these tests are
   mostly about the button being disabled for exactly the cases the server
   refuses — and about the confirmation describing what actually happens to the
   person's work, since that is the thing being decided. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminApp from "./AdminApp";
import { useOS } from "../store";

vi.mock("../lib/api", () => ({
  apiUsers: vi.fn(), apiCreateUser: vi.fn(), apiUpdateUser: vi.fn(),
  apiRemovalPreview: vi.fn(), apiRemoveUser: vi.fn(),
  apiAiUsage: vi.fn(), apiWorkspaces: vi.fn(), apiSetWorkspaceStatus: vi.fn(),
  apiDeleteWorkspace: vi.fn(), apiDeleteOwnWorkspace: vi.fn(),
}));
import { apiRemovalPreview, apiRemoveUser, apiUsers } from "../lib/api";

const ADMIN = { id: "u-admin", email: "ada@co.dev", full_name: "Ada Admin", role: "admin",
                is_active: true, avatar_hue: 200, created_at: "2026-01-01" };
const HR = { ...ADMIN, id: "u-hr", email: "hazel@co.dev", full_name: "Hazel HR", role: "hr" };
const MANAGER = { ...ADMIN, id: "u-mgr", email: "milo@co.dev", full_name: "Milo Manager", role: "manager" };
const EMPLOYEE = { ...ADMIN, id: "u-emp", email: "eli@co.dev", full_name: "Eli Employee", role: "employee" };

const PREVIEW = {
  allowed: true, reason: "",
  counts: { documents: 12, automations: 3, agents: 1, tasks: 7,
            assigned_tasks: 2, conversations: 19, connectors: 1 },
};

function signedInAs(user: typeof ADMIN) {
  useOS.setState({ user: user as never, token: "t", orgName: "Acme", phase: "desktop", isOwner: false });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(apiUsers).mockResolvedValue([ADMIN, HR, MANAGER, EMPLOYEE] as never);
  vi.mocked(apiRemovalPreview).mockResolvedValue(PREVIEW as never);
  vi.mocked(apiRemoveUser).mockResolvedValue({
    removed: EMPLOYEE.email, full_name: EMPLOYEE.full_name, reassigned: {},
  } as never);
  signedInAs(ADMIN);
});

const removeBtn = async (email: string) =>
  (await screen.findByTestId(`remove-${email}`)) as HTMLButtonElement;

describe("the remove action", () => {
  it("is offered for every role an admin manages", async () => {
    render(<AdminApp />);
    for (const u of [HR, MANAGER, EMPLOYEE]) {
      expect((await removeBtn(u.email)).disabled).toBe(false);
    }
  });

  it("cannot be used on yourself", async () => {
    render(<AdminApp />);
    const btn = await removeBtn(ADMIN.email);
    expect(btn.disabled).toBe(true);
    expect(btn.title).toMatch(/your own account/i);
  });

  it("still allows removing an admin who has already been deactivated", async () => {
    // The tempting version of the last-admin rule counts active admins without
    // excluding the one being removed — which blocks this, even though the
    // signed-in admin plainly remains. The rule has to ask "is there another
    // active admin *once this one is gone*".
    const dormant = { ...ADMIN, id: "u-old", email: "old@co.dev",
                      full_name: "Old Admin", is_active: false };
    vi.mocked(apiUsers).mockResolvedValue([ADMIN, dormant, EMPLOYEE] as never);
    render(<AdminApp />);
    const btn = await removeBtn(dormant.email);
    expect(btn.disabled).toBe(false);
    expect(btn.title).not.toMatch(/last admin/i);
  });

  it("lets an admin be removed when another one remains", async () => {
    const second = { ...ADMIN, id: "u-admin-2", email: "alt@co.dev", full_name: "Alt Admin" };
    vi.mocked(apiUsers).mockResolvedValue([ADMIN, second, EMPLOYEE] as never);
    render(<AdminApp />);
    expect((await removeBtn(second.email)).disabled).toBe(false);
  });

  it("does not let HR remove admin or HR accounts", async () => {
    signedInAs(HR);
    render(<AdminApp />);
    expect((await removeBtn(ADMIN.email)).disabled).toBe(true);
    expect((await removeBtn(HR.email)).disabled).toBe(true);
    expect((await removeBtn(MANAGER.email)).disabled).toBe(false);
    expect((await removeBtn(EMPLOYEE.email)).disabled).toBe(false);
  });
});

describe("the confirmation", () => {
  it("asks before doing anything", async () => {
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    await screen.findByTestId("remove-dialog");
    expect(apiRemoveUser).not.toHaveBeenCalled();
  });

  it("says what moves to you and what is deleted", async () => {
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    const dialog = await screen.findByTestId("remove-dialog");

    await waitFor(() => expect(dialog.textContent).toContain("12 document(s)"));
    expect(dialog.textContent).toContain("Moves to you");
    expect(dialog.textContent).toContain("3 automation(s)");
    expect(dialog.textContent).toContain("Deleted with the account");
    expect(dialog.textContent).toContain("19 chat conversation(s)");
  });

  it("points at deactivation as the reversible option", async () => {
    // Most removals people reach for are actually "pause this person".
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    const dialog = await screen.findByTestId("remove-dialog");
    expect(dialog.textContent).toMatch(/Active toggle/i);
    expect(dialog.textContent).toMatch(/frees their seat/i);
  });

  it("promises the audit trail survives", async () => {
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    const dialog = await screen.findByTestId("remove-dialog");
    expect(dialog.textContent).toMatch(/audit trail keeps every action/i);
  });

  it("removes the person and takes them off the list once confirmed", async () => {
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    fireEvent.click(await screen.findByTestId("confirm-remove"));

    await waitFor(() => expect(apiRemoveUser).toHaveBeenCalledWith(EMPLOYEE.id));
    await waitFor(() => expect(screen.queryByTestId(`remove-${EMPLOYEE.email}`)).toBeNull());
    expect(screen.queryByTestId("remove-dialog")).toBeNull();
  });

  it("can be cancelled without touching the account", async () => {
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    await screen.findByTestId("remove-dialog");
    fireEvent.click(screen.getByRole("button", { name: /^Cancel$/i }));

    await waitFor(() => expect(screen.queryByTestId("remove-dialog")).toBeNull());
    expect(apiRemoveUser).not.toHaveBeenCalled();
    expect(await removeBtn(EMPLOYEE.email)).toBeTruthy();
  });

  it("keeps the person on the list if the server refuses", async () => {
    vi.mocked(apiRemoveUser).mockRejectedValue(new Error("This is the last active admin."));
    render(<AdminApp />);
    fireEvent.click(await removeBtn(EMPLOYEE.email));
    fireEvent.click(await screen.findByTestId("confirm-remove"));

    expect(await screen.findByText("This is the last active admin.")).toBeTruthy();
    expect(screen.getByTestId("remove-dialog")).toBeTruthy();
    expect(await removeBtn(EMPLOYEE.email)).toBeTruthy();
  });
});
