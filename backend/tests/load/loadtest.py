"""Dependency-light load harness (httpx + asyncio) — same scenario as the
locustfile, no Locust required. Prints RPS + latency percentiles.

    python backend/tests/load/loadtest.py --base http://localhost:8000 \
           --users 50 --seconds 20
"""
import argparse
import asyncio
import random
import statistics
import time

import httpx

QUESTIONS = [
    "How many annual leave days do we get?",
    "Can I carry forward unused leave?",
    "Summarize Q3 revenue performance",
    "What is the backup procedure for Atlas?",
    "What is a SEV-1 incident and who do I notify?",
]


async def worker(base: str, token: str, deadline: float, latencies: list, errors: list) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=base, timeout=30, trust_env=False) as client:
        while time.perf_counter() < deadline:
            kind = random.random()
            t0 = time.perf_counter()
            try:
                if kind < 0.6:
                    r = await client.post("/api/chat", headers=headers,
                                          json={"message": random.choice(QUESTIONS)})
                elif kind < 0.8:
                    r = await client.get("/api/documents", headers=headers)
                else:
                    r = await client.get("/api/graph?limit=40", headers=headers)
                if r.status_code == 429:
                    errors.append("429")
                    await asyncio.sleep(1)
                    continue
                r.raise_for_status()
                latencies.append((time.perf_counter() - t0) * 1000)
            except Exception as exc:  # noqa: BLE001
                errors.append(type(exc).__name__)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=20)
    args = ap.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30, trust_env=False) as client:
        r = await client.post("/api/auth/login",
                              json={"email": "admin@eaios.dev", "password": "admin12345"})
        r.raise_for_status()
        token = r.json()["token"]["access_token"]

    latencies: list[float] = []
    errors: list[str] = []
    deadline = time.perf_counter() + args.seconds
    t0 = time.perf_counter()
    await asyncio.gather(*(worker(args.base, token, deadline, latencies, errors)
                           for _ in range(args.users)))
    elapsed = time.perf_counter() - t0

    lat = sorted(latencies)
    pct = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0  # noqa: E731
    print(f"users={args.users} duration={elapsed:.1f}s requests={len(lat)} errors={len(errors)}")
    print(f"throughput={len(lat) / elapsed:.1f} req/s")
    print(f"latency ms: p50={pct(0.50):.0f} p90={pct(0.90):.0f} p95={pct(0.95):.0f} "
          f"p99={pct(0.99):.0f} max={lat[-1]:.0f}" if lat else "no successful requests")
    if errors:
        from collections import Counter

        print("errors:", dict(Counter(errors)))


if __name__ == "__main__":
    asyncio.run(main())
