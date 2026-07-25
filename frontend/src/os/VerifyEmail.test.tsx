/* The verification gate, exercised the way a person uses it.

   A browser run of this flow once reported that the API had accepted the code
   while the screen stayed on the gate — the kind of gap a server test cannot
   see, because the server was never the part that was wrong. These tests drive
   the real DOM: type into the field, click the button, and assert on what the
   application state becomes. */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VerifyEmail from "./VerifyEmail";
import { useOS } from "../store";

vi.mock("../lib/api", () => ({
  apiVerifyEmail: vi.fn(),
  apiResendCode: vi.fn(),
}));
import { apiResendCode, apiVerifyEmail } from "../lib/api";

const USER = { id: "u1", email: "owner@acme.dev", full_name: "Owner One", role: "admin", avatar_hue: 200 };

function session(overrides: Record<string, unknown> = {}) {
  return { user: USER, token: "tok", live: true, orgName: "Acme Co",
           isOwner: false, industry: "", emailVerified: true, ...overrides };
}

beforeEach(() => {
  vi.clearAllMocks();
  useOS.setState({ user: USER as never, token: "tok", orgName: "Acme Co",
                   emailVerified: false, phase: "desktop" });
});

/** Type a code the way a person does, one keystroke at a time. */
function enterCode(value: string) {
  fireEvent.change(screen.getByTestId("verify-code"), { target: { value } });
}

const submitBtn = () => screen.getByRole("button", { name: /verify and continue/i });

describe("the verification gate", () => {
  it("says which address the code went to", () => {
    render(<VerifyEmail />);
    expect(screen.getByText("owner@acme.dev")).toBeTruthy();
    expect(screen.getByText(/Acme Co/)).toBeTruthy();
  });

  it("keeps the button disabled until six digits are present", () => {
    render(<VerifyEmail />);
    expect((submitBtn() as HTMLButtonElement).disabled).toBe(true);
    enterCode("1234");
    expect((submitBtn() as HTMLButtonElement).disabled).toBe(true);
    enterCode("123456");
    expect((submitBtn() as HTMLButtonElement).disabled).toBe(false);
  });

  it("ignores anything that isn't a digit, so a pasted code still works", () => {
    render(<VerifyEmail />);
    enterCode("12-34 56abc");
    expect((screen.getByTestId("verify-code") as HTMLInputElement).value).toBe("123456");
  });

  it("unlocks the workspace once the right code is accepted", async () => {
    // The assertion the browser run left unresolved: the screen has to hand
    // control back, not merely let the request succeed.
    vi.mocked(apiVerifyEmail).mockResolvedValue(session() as never);
    render(<VerifyEmail />);
    enterCode("750007");
    fireEvent.click(submitBtn());

    await waitFor(() => expect(useOS.getState().emailVerified).toBe(true));
    expect(apiVerifyEmail).toHaveBeenCalledWith("owner@acme.dev", "750007");
    expect(useOS.getState().phase).toBe("desktop");
  });

  it("stays on the gate if the server still says unverified", async () => {
    // Trusting a 200 rather than the server's answer would drop someone onto a
    // desktop where every request fails.
    vi.mocked(apiVerifyEmail).mockResolvedValue(session({ emailVerified: false }) as never);
    render(<VerifyEmail />);
    enterCode("750007");
    fireEvent.click(submitBtn());

    await waitFor(() => expect(apiVerifyEmail).toHaveBeenCalled());
    expect(useOS.getState().emailVerified).toBe(false);
  });

  it("explains a wrong code and clears the field to retype", async () => {
    vi.mocked(apiVerifyEmail).mockRejectedValue(new Error("That code isn't right. 5 attempts left."));
    render(<VerifyEmail />);
    enterCode("000000");
    fireEvent.click(submitBtn());

    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent", "That code isn't right. 5 attempts left.");
    expect(useOS.getState().emailVerified).toBe(false);
    expect((screen.getByTestId("verify-code") as HTMLInputElement).value).toBe("");
  });

  it("offers a new code and then holds off, so resend can't be hammered", async () => {
    vi.mocked(apiResendCode).mockResolvedValue({ ok: true, detail: "sent" } as never);
    render(<VerifyEmail />);
    const resend = screen.getByRole("button", { name: /send a new code/i });
    fireEvent.click(resend);

    await waitFor(() => expect(apiResendCode).toHaveBeenCalledWith("owner@acme.dev"));
    const cooling = await screen.findByRole("button", { name: /resend in/i });
    expect((cooling as HTMLButtonElement).disabled).toBe(true);
  });

  it("lets someone who mistyped their address start over", () => {
    render(<VerifyEmail />);
    fireEvent.click(screen.getByRole("button", { name: /use a different email/i }));
    expect(useOS.getState().phase).toBe("login");
    expect(useOS.getState().token).toBe(null);
  });
});
