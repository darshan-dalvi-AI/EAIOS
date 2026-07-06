"""Locust load test — Phase 6 target: 100 concurrent chat users.

Run:
    pip install locust
    locust -f backend/tests/load/locustfile.py --host http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 2m --headless

Note: RATE_LIMIT_ENABLED=0 (env) when load testing, or the chat bucket
(60/min/user) throttles by design — each Locust user logs in separately,
so light runs stay under the limit.
"""
import random

from locust import HttpUser, between, task

QUESTIONS = [
    "How many annual leave days do we get?",
    "Can I carry forward unused leave?",
    "Summarize Q3 revenue performance",
    "What is the backup procedure for Atlas?",
    "What is a SEV-1 incident and who do I notify?",
    "documents by type",
]


class ChatUser(HttpUser):
    wait_time = between(1, 4)
    token: str = ""

    def on_start(self) -> None:
        r = self.client.post("/api/auth/login",
                             json={"email": "admin@eaios.dev", "password": "admin12345"})
        r.raise_for_status()
        self.token = r.json()["token"]["access_token"]

    @property
    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(6)
    def chat(self) -> None:
        self.client.post("/api/chat", headers=self._auth,
                         json={"message": random.choice(QUESTIONS)}, name="/api/chat")

    @task(2)
    def documents(self) -> None:
        self.client.get("/api/documents", headers=self._auth, name="/api/documents")

    @task(1)
    def graph(self) -> None:
        self.client.get("/api/graph?limit=40", headers=self._auth, name="/api/graph")

    @task(1)
    def traces(self) -> None:
        self.client.get("/api/traces", headers=self._auth, name="/api/traces")
