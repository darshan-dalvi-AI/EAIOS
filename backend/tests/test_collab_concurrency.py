"""Several people editing one file at the same time.

The product claim is that a team can work in the same file simultaneously
without overwriting each other. That rests on two things being true:

  * the relay hands every editor's update to all the others, and
  * everyone in the room is visible to everyone else.

These tests drive the real WebSocket endpoint with five concurrent clients —
the number the smallest paid plan seats — and assert both.
"""
import secrets

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PW = "ConcurrencyPass!2026"
EDITORS = 5


def _workspace() -> tuple[dict, str]:
    tag = secrets.token_hex(4)
    r = client.post("/api/auth/signup", json={
        "company_name": f"Concurrent {tag}", "full_name": "Lead",
        "email": f"lead-{tag}@concurrent.com", "password": PW})
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return {"Authorization": "Bearer " + body["token"]["access_token"]}, body["token"]["access_token"]


def _extra_member(admin: dict, n: int) -> str:
    tag = secrets.token_hex(4)
    email = f"dev{n}-{tag}@concurrent.com"
    made = client.post("/api/users", headers=admin, json={
        "email": email, "full_name": f"Dev {n}", "password": PW, "role": "employee"})
    assert made.status_code in (200, 201), made.text
    login = client.post("/api/auth/login", json={"email": email, "password": PW})
    return login.json()["token"]["access_token"]


@pytest.fixture
def shared_file():
    """One file, plus five tokens belonging to five different people."""
    admin, admin_token = _workspace()
    project = client.post("/api/projects", headers=admin, json={"name": "Team"}).json()
    f = client.post(f"/api/projects/{project['id']}/files", headers=admin,
                    json={"path": "shared.py", "content": "# shared\n"}).json()
    tokens = [admin_token] + [_extra_member(admin, i) for i in range(1, EDITORS)]
    return {"file_id": f["id"], "tokens": tokens}


def test_five_people_can_hold_the_same_file_open(shared_file):
    """Five sockets on one file, and each is told about the other four."""
    from contextlib import ExitStack

    file_id = shared_file["file_id"]
    with ExitStack() as stack:
        sockets = [
            stack.enter_context(client.websocket_connect(
                f"/api/ws/collab/{file_id}?token={tok}"))
            for tok in shared_file["tokens"]
        ]
        assert len(sockets) == EDITORS

        # The last socket to arrive should see the whole room.
        peers_seen = 0
        for _ in range(EDITORS * 2 + 2):
            msg = sockets[-1].receive()
            if msg.get("type") == "websocket.disconnect":
                break
            text = msg.get("text")
            if not text:
                continue
            import json
            data = json.loads(text)
            if data.get("type") == "collab.peers":
                peers_seen = max(peers_seen, len(data.get("peers", [])))
                if peers_seen >= EDITORS:
                    break
        assert peers_seen == EDITORS, (
            f"only {peers_seen} of {EDITORS} editors were visible in the room")


def test_an_edit_reaches_every_other_editor(shared_file):
    """What one person types must arrive at all the others — that is the whole
    point of the relay. The payload is opaque CRDT bytes; the test asserts it is
    delivered, not what it means."""
    from contextlib import ExitStack

    file_id = shared_file["file_id"]
    update = bytes([1, 2, 3, 4, 5, 6, 7, 8])

    with ExitStack() as stack:
        sockets = [
            stack.enter_context(client.websocket_connect(
                f"/api/ws/collab/{file_id}?token={tok}"))
            for tok in shared_file["tokens"]
        ]
        sockets[0].send_bytes(update)

        for i, sock in enumerate(sockets[1:], start=1):
            got = None
            for _ in range(EDITORS * 3 + 4):
                msg = sock.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    got = msg["bytes"]
                    break
            assert got == update, f"editor {i} never received the other's edit"


def test_the_sender_does_not_receive_its_own_edit(shared_file):
    """Echoing an update back to its author would apply it twice."""
    from contextlib import ExitStack

    file_id = shared_file["file_id"]
    with ExitStack() as stack:
        a = stack.enter_context(client.websocket_connect(
            f"/api/ws/collab/{file_id}?token={shared_file['tokens'][0]}"))
        b = stack.enter_context(client.websocket_connect(
            f"/api/ws/collab/{file_id}?token={shared_file['tokens'][1]}"))

        a.send_bytes(b"\x09\x09")
        # b gets it...
        seen_b = None
        for _ in range(8):
            msg = b.receive()
            if msg.get("bytes") is not None:
                seen_b = msg["bytes"]
                break
        assert seen_b == b"\x09\x09"

        # ...and a is only ever sent control frames, never its own bytes back.
        a.send_text("ping")
        for _ in range(6):
            msg = a.receive()
            assert msg.get("bytes") != b"\x09\x09", "the author received its own update"
            if msg.get("text") and "pong" in msg["text"]:
                break


def test_a_file_in_another_workspace_cannot_be_joined():
    """The room is per file, so joining one is a tenant decision."""
    admin_a, _ = _workspace()
    project = client.post("/api/projects", headers=admin_a, json={"name": "Private"}).json()
    f = client.post(f"/api/projects/{project['id']}/files", headers=admin_a,
                    json={"path": "secret.py", "content": "KEY = 1\n"}).json()

    _, intruder_token = _workspace()          # a different company entirely
    with pytest.raises(Exception):
        with client.websocket_connect(
                f"/api/ws/collab/{f['id']}?token={intruder_token}") as ws:
            ws.receive()
