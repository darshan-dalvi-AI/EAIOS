"""WebRTC signaling relay over the realtime WebSocket (video calls)."""
import json

from fastapi.testclient import TestClient

from app.main import app


def client() -> TestClient:
    return TestClient(app)


def _token(c: TestClient, email: str, pw: str) -> tuple[str, str]:
    r = c.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    body = r.json()
    return body["token"]["access_token"], body["user"]["id"]


def _drain_until(ws, wanted_type: str, tries: int = 40) -> dict:
    """Skip presence/replay frames until a frame of the wanted type arrives.
    (Connecting replays up to 20 ring-buffer events, so the budget must be
    comfortably larger when the full suite has already populated the hub.)"""
    for _ in range(tries):
        ev = json.loads(ws.receive_text())
        if ev.get("type") == wanted_type:
            return ev
    raise AssertionError(f"never received {wanted_type}")


def test_rtc_relay_between_two_users():
    with client() as c:
        c.post("/api/auth/register",
               json={"email": "callee@test.dev", "full_name": "Callee User", "password": "password123"})
        tok_a, id_a = _token(c, "admin@eaios.dev", "admin12345")
        tok_b, id_b = _token(c, "callee@test.dev", "password123")

        with c.websocket_connect(f"/api/ws?token={tok_a}") as ws_a, \
             c.websocket_connect(f"/api/ws?token={tok_b}") as ws_b:
            # A rings B → B receives the ring with A's identity attached
            ws_a.send_text(json.dumps({"type": "rtc.ring", "to": id_b, "payload": {"call": "video"}}))
            ring = _drain_until(ws_b, "rtc.ring")
            assert ring["from"]["id"] == id_a
            assert ring["from"]["name"]
            assert ring["payload"]["call"] == "video"

            # B answers with an SDP payload → A receives it relayed untouched
            ws_b.send_text(json.dumps({"type": "rtc.answer", "to": id_a, "payload": {"sdp": "v=0 demo-answer"}}))
            ans = _drain_until(ws_a, "rtc.answer")
            assert ans["from"]["id"] == id_b
            assert ans["payload"]["sdp"] == "v=0 demo-answer"

            # ICE + captions + end all ride the same relay
            ws_a.send_text(json.dumps({"type": "rtc.caption", "to": id_b, "payload": {"text": "hello from A"}}))
            cap = _drain_until(ws_b, "rtc.caption")
            assert cap["payload"]["text"] == "hello from A"


def test_rtc_ring_offline_target_reports_unavailable():
    with client() as c:
        tok_a, _ = _token(c, "admin@eaios.dev", "admin12345")
        with c.websocket_connect(f"/api/ws?token={tok_a}") as ws_a:
            ws_a.send_text(json.dumps({"type": "rtc.ring", "to": "no-such-user", "payload": {}}))
            ev = _drain_until(ws_a, "rtc.unavailable")
            assert ev["payload"]["to"] == "no-such-user"


def test_rtc_requires_target_and_type_prefix():
    with client() as c:
        c.post("/api/auth/register",
               json={"email": "callee2@test.dev", "full_name": "Callee Two", "password": "password123"})
        tok_a, _ = _token(c, "admin@eaios.dev", "admin12345")
        tok_b, id_b = _token(c, "callee2@test.dev", "password123")
        with c.websocket_connect(f"/api/ws?token={tok_a}") as ws_a, \
             c.websocket_connect(f"/api/ws?token={tok_b}") as ws_b:
            # missing "to" → dropped; malformed type → dropped; then a valid one arrives
            ws_a.send_text(json.dumps({"type": "rtc.offer", "payload": {"sdp": "x"}}))
            ws_a.send_text(json.dumps({"type": "rtcbogus", "to": id_b, "payload": {}}))
            ws_a.send_text(json.dumps({"type": "rtc.end", "to": id_b, "payload": {}}))
            ev = _drain_until(ws_b, "rtc.end")
            assert ev["type"] == "rtc.end"
