"""The code sandbox is only safe because of its headers, so the headers are tested.

Executing user-authored code in a *collaborative* editor means person B can put
code in a file that person A runs. Every assertion here is about making that
harmless: if one of these regresses, B's code gains A's session.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.api.routes.runner import (
    BOOT_TIMEOUT_MS, DEFAULT_TIMEOUT_MS, MAX_OUTPUT_CHARS, MAX_TIMEOUT_MS,
    PYODIDE_URL, SANDBOX_CSP, runner_html,
)
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _csp(client: TestClient) -> dict[str, str]:
    r = client.get("/api/code/runner")
    assert r.status_code == 200
    parts = [p.strip() for p in r.headers["content-security-policy"].split(";")]
    return {p.split(" ")[0]: p for p in parts if p}


# ── the isolation guarantees ──────────────────────────────────────────────

def test_sandbox_cannot_reach_this_application(client):
    """No 'self' anywhere. The sandbox may fetch a CDN and nothing else.

    This is the load-bearing assertion. In an opaque origin 'self' matches
    nothing anyway, but granting it would signal the wrong intent to the next
    person editing this policy — and would be live the moment somebody removed
    the sandbox attribute.
    """
    directives = _csp(client)
    for name, value in directives.items():
        if name == "frame-ancestors":
            continue        # 'self' here means "only EAIOS may embed it"
        assert "'self'" not in value, f"{name} grants the sandbox same-origin access"


def test_sandbox_default_denies_everything(client):
    assert _csp(client)["default-src"] == "default-src 'none'"


def test_only_the_pinned_cdn_is_reachable(client):
    directives = _csp(client)
    hosts = re.findall(r"https?://[^\s;]+", " ".join(directives.values()))
    assert set(hosts) == {"https://cdn.jsdelivr.net"}


def test_pyodide_version_is_pinned(client):
    """A floating version would let an upstream release change what executes
    inside the sandbox with no deploy here."""
    assert re.fullmatch(r"https://cdn\.jsdelivr\.net/pyodide/v\d+\.\d+\.\d+/full/",
                        PYODIDE_URL), PYODIDE_URL
    assert "@latest" not in PYODIDE_URL


def test_execution_happens_in_a_terminable_worker(client):
    """`while True: pass` has no cooperative exit; terminate() is the only way
    out, and that needs a worker. worker-src must therefore allow blob:."""
    directives = _csp(client)
    assert "blob:" in directives["worker-src"]
    assert "terminate()" in runner_html()


def test_the_app_can_frame_it_but_nobody_else_can(client):
    r = client.get("/api/code/runner")
    assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
    # The app-wide default is DENY, which would block EAIOS framing its own
    # sandbox; SAMEORIGIN is the narrowest value that still works.
    assert r.headers["x-frame-options"] == "SAMEORIGIN"


def test_the_page_never_grants_itself_same_origin(client):
    """A sandbox that is allowed both allow-scripts and allow-same-origin can
    reach out and delete its own sandbox attribute. Neither the document nor
    the client that embeds it may ask for that pair."""
    assert "allow-same-origin" not in runner_html()


def test_runner_serves_no_workspace_data(client):
    """Unauthenticated by design, so it must be a static shell. If this ever
    returns something tenant-shaped, the endpoint needs a session."""
    body = client.get("/api/code/runner").text
    for leak in ("org_id", "user_id", "token", "@eaios.dev", "postgres"):
        assert leak not in body


# ── the runaway-program limits ────────────────────────────────────────────

def test_limits_are_ordered_sensibly():
    assert 0 < DEFAULT_TIMEOUT_MS <= MAX_TIMEOUT_MS
    # Downloading ~10 MB of CPython is not a runaway program: the boot clock
    # has to outlast the execution clock or every cold Python run is killed.
    assert BOOT_TIMEOUT_MS > MAX_TIMEOUT_MS
    assert MAX_OUTPUT_CHARS > 0


def test_the_document_carries_its_own_limits():
    """The limits must reach the browser as literals — a page that shipped the
    placeholders would fall back to whatever `undefined` coerces to."""
    html = runner_html()
    assert "__WORKER_SRC__" not in html and "__MAX_TIMEOUT__" not in html
    assert "__BOOT_TIMEOUT__" not in html and "__PYODIDE_URL__" not in html
    assert str(MAX_TIMEOUT_MS) in html and str(BOOT_TIMEOUT_MS) in html


def test_worker_source_cannot_break_out_of_the_script_tag():
    """The worker is inlined as a JS string literal. A stray '</script>' in it
    would be honoured by the HTML parser and end the block early."""
    html = runner_html()
    assert html.count("</script>") == 1


def test_only_the_embedder_can_drive_the_sandbox():
    """A run request from any other frame must be ignored, otherwise a hostile
    embed could use the sandbox as an execution service."""
    assert "e.source !== parent" in runner_html()


# ── the policy is not weakened for the rest of the app ────────────────────

def test_the_main_app_csp_is_untouched(client):
    """The sandbox's permissions must not leak onto normal pages: those hold a
    real session, and 'unsafe-eval' there would be exactly the XSS the sandbox
    exists to avoid."""
    main = client.get("/api/health").headers["content-security-policy"]
    assert "unsafe-eval" not in main
    assert "cdn.jsdelivr.net" not in main
    assert main != SANDBOX_CSP
