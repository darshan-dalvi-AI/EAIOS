"""COOP must not sever the opener for Google's sign-in popup.

Google's popup finishes by postMessage-ing the ID token back to the window
that opened it. `Cross-Origin-Opener-Policy: same-origin` makes that window
`null` from the popup's side, so the credential has nowhere to go: the person
signs in successfully and the popup then sits on accounts.google.com/gsi/
transform, blank, indefinitely.

`same-origin-allow-popups` is the documented value for a site doing OAuth in a
popup. It still stops other origins reaching into this window; it only lets
popups this app itself opened keep their opener reference.

The test guards the direction of the mistake — `same-origin` is the tempting,
stricter-looking value, and someone hardening headers later would reach for it.
"""
from app.core.headers import BASE_HEADERS, CSP


def test_coop_allows_the_google_popup_to_reach_its_opener():
    coop = BASE_HEADERS["Cross-Origin-Opener-Policy"]
    assert coop == "same-origin-allow-popups", (
        f"COOP is {coop!r}. Plain 'same-origin' severs window.opener for "
        "cross-origin popups and silently breaks Google sign-in — the popup "
        "hangs blank after a successful login."
    )


def test_coop_is_still_set_at_all():
    """allow-popups is a relaxation, not an removal: unset would be worse."""
    assert "Cross-Origin-Opener-Policy" in BASE_HEADERS


def test_csp_still_permits_google_identity_services():
    """The popup is only half of it — the script and frame must be allowed too."""
    for directive in ("script-src", "frame-src", "connect-src"):
        line = next(p for p in CSP.split("; ") if p.startswith(directive))
        assert "accounts.google.com" in line, (
            f"{directive} does not allow accounts.google.com, so Google "
            "sign-in cannot load."
        )


def test_clickjacking_defences_survived_the_change():
    """Relaxing COOP must not have relaxed anything else by accident."""
    assert BASE_HEADERS["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in CSP
    assert "object-src 'none'" in CSP
    assert "form-action 'self'" in CSP
