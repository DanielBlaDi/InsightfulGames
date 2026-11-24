import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

HOST = os.getenv("PROXY_HOST", "127.0.0.1")
MOBILE_PORT = int(os.getenv("MOBILE_HTTPS_PORT", "8443"))
LIMIT = 5
WINDOW_SECONDS = 60
ATTACK_REQUESTS = 20


def percentile(values: list[float], percentage: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((percentage / 100) * (len(ordered) - 1))
    return round(ordered[max(0, min(index, len(ordered) - 1))], 1)


async def login_user(base_url: str, prefix: str) -> str:
    username = f"{prefix}-{uuid.uuid4().hex[:8]}"
    transport = httpx.AsyncHTTPTransport(verify=False)
    async with httpx.AsyncClient(base_url=base_url, timeout=20, transport=transport) as client:
        registered = await client.post(
            "/auth/register",
            json={"username": username, "password": "Clave-Segura-123"},
        )
        registered.raise_for_status()
        logged = await client.post(
            "/auth/login",
            json={"username": username, "password": "Clave-Segura-123"},
        )
        logged.raise_for_status()
        return logged.json()["accessToken"]


async def measure_repetition(repetition: int) -> dict:
    base_url = f"https://{HOST}:{MOBILE_PORT}"
    transport = httpx.AsyncHTTPTransport(verify=False)
    async with httpx.AsyncClient(base_url=base_url, timeout=20, transport=transport) as client:
        attacker_token = await login_user(base_url, f"rl-a{repetition}")
        legitimate_token = await login_user(base_url, f"rl-l{repetition}")
        payload = {"mode": "local", "timeControl": {"minutes": 10}, "visibility": "private"}
        latencies = []
        statuses = []
        legitimate_statuses = []
        started = time.monotonic()

        for _ in range(ATTACK_REQUESTS):
            request_started = time.monotonic()
            response = await client.post(
                "/games",
                json=payload,
                headers={"Authorization": f"Bearer {attacker_token}"},
            )
            latencies.append((time.monotonic() - request_started) * 1000)
            statuses.append(response.status_code)

        for _ in range(5):
            response = await client.post(
                "/games",
                json=payload,
                headers={"Authorization": f"Bearer {legitimate_token}"},
            )
            legitimate_statuses.append(response.status_code)

        elapsed = time.monotonic() - started

    blocked = statuses.count(429)
    accepted = sum(status != 429 for status in statuses)
    return {
        "repetition": repetition,
        "attempts": len(statuses),
        "accepted_or_other": accepted,
        "blocked_429": blocked,
        "pct_blocked": round(100 * blocked / len(statuses), 1),
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "duration_s": round(elapsed, 3),
        "statuses": statuses,
        "legitimate_attempts": len(legitimate_statuses),
        "legitimate_ok": sum(status in (200, 201, 202) for status in legitimate_statuses),
    }


async def main() -> None:
    repetitions = int(os.getenv("RATE_LIMIT_REPETITIONS", "5"))
    results = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entorno": "Docker Compose",
        "parametros": {
            "limite": LIMIT,
            "ventana_segundos": WINDOW_SECONDS,
            "intentos_por_corrida": ATTACK_REQUESTS,
            "repeticiones": repetitions,
        },
        "corridas": [],
    }

    for repetition in range(1, repetitions + 1):
        print(f"Medicion {repetition}/{repetitions}...")
        results["corridas"].append(await measure_repetition(repetition))
        await asyncio.sleep(1)

    output = Path(__file__).with_name("resultados.json")
    output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
