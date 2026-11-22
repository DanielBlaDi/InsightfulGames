"""Mide los escenarios de seguridad del reverse proxy (táctica "resistir ataques") contra el stack en Docker.

    python medir_resistencia.py                # escribe resultados.json junto a este archivo

Necesita el stack levantado (docker compose up -d), httpx y el CLI de docker. Por cada entrada del proxy
(web :FRONTEND_PORT y móvil :MOBILE_GATEWAY_PORT) ejecuta:

  S1  Fuerza bruta en el login: N intentos con contraseña errónea lo más rápido posible desde el host, mientras
      un usuario legítimo inicia sesión desde OTRA IP (un contenedor de la red interna). Cuenta cuántos frena
      nginx (429) y cuántos llegan a Auth (401).
  S2  Acceso a lo interno: variantes de /internal (mayúsculas, codificadas, con "..", barras dobles) enviadas
      con un cliente HTTP crudo (sin normalizar la ruta) y conexión TCP directa a los puertos de los servicios.
      "Llegó a un gateway" se cuenta en los logs de los gateways, no por la respuesta.
  S3  Suplantación: un usuario autenticado manda X-User-Id con el id de la víctima (varias grafías); y sin
      token. Cuenta respuestas que devuelven datos de la víctima.
"""

import asyncio
import json
import os
import socket
import statistics
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

HOST = os.getenv("PROXY_HOST", "localhost")
WEB_PORT = int(os.getenv("FRONTEND_PORT", "80"))
MOBILE_PORT = int(os.getenv("MOBILE_GATEWAY_PORT", "8090"))
BRUTE_FORCE_ATTEMPTS = int(os.getenv("BRUTE_FORCE_ATTEMPTS", "300"))
BRUTE_FORCE_CONCURRENCY = 50
LEGIT_CONTAINER = os.getenv("LEGIT_CONTAINER", "api-gateway-mobile")  # cliente legítimo con otra IP
GATEWAY_CONTAINERS = ["api-gateway-component", "api-gateway-mobile"]
PASSWORD = "Clave-Segura-123"

ENTRIES = {
    "web": {
        "port": WEB_PORT,
        "internal_port": 8000,  # puerto de nginx dentro de la red de Docker
        "prefix": "/api",
        "protected": ["/api/profile/me", "/api/stats/me", "/api/games"],
    },
    "movil": {
        "port": MOBILE_PORT,
        "internal_port": 8090,
        "prefix": "",
        "protected": ["/profile/me", "/stats/me", "/games", "/home"],
    },
}

# Puertos de los servicios internos (y de depuración) que NO deben estar publicados en el host
SERVICE_PORTS = {
    8080: "api-gateway web", 8081: "auth", 8082: "game-logic", 8083: "single-player", 8084: "multiplayer",
    8085: "tutor", 8086: "botcito", 8087: "profile-stats", 8091: "gateway móvil (debug)",
    27017: "mongo", 27018: "mongo-analysis", 3306: "mysql", 5432: "postgres", 5672: "rabbitmq",
    15672: "rabbitmq admin",
}


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return round(ordered[k], 1)


def base(entry):
    return f"http://{HOST}:{ENTRIES[entry]['port']}"


# ----------------------------------------------------------------------------------------- usuarios


def make_user(entry, prefix):
    """Registra un usuario y devuelve {username, userId, token}. Usa la entrada móvil (Bearer, sin cookie)."""
    username = prefix + uuid.uuid4().hex[:8]
    with httpx.Client(base_url=base("movil"), timeout=20) as client:
        r = client.post("/auth/register", json={"username": username, "password": PASSWORD})
        r.raise_for_status()
        r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
        r.raise_for_status()
        body = r.json()
    return {"username": username, "userId": body["user"]["userId"], "token": body["accessToken"]}


def seed_victim_game(victim):
    """La víctima tiene una partida, así su historial se distingue del del atacante."""
    with httpx.Client(base_url=base("movil"), timeout=20) as client:
        r = client.post("/games", json={"mode": "local", "timeControl": None},
                        headers={"Authorization": f"Bearer {victim['token']}"})
        r.raise_for_status()
        return r.json()["gameId"]


# --------------------------------------------------------------------------------------- S1 fuerza bruta

LEGIT_CLIENT = r"""
import json, sys, time, urllib.request, urllib.error
url, user, pwd, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
out = []
for _ in range(n):
    req = urllib.request.Request(url, data=json.dumps({"username": user, "password": pwd}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        status = 0
    out.append([status, (time.perf_counter() - t) * 1000])
    time.sleep(0.15)
print(json.dumps(out))
"""


async def brute_force(entry, victim):
    cfg = ENTRIES[entry]
    url = f"{base(entry)}{cfg['prefix']}/auth/login"
    internal_url = f"http://reverse-proxy:{cfg['internal_port']}{cfg['prefix']}/auth/login"

    # Usuario legítimo desde otra IP (contenedor de la red interna), en paralelo con el ataque
    legit = await asyncio.create_subprocess_exec(
        "docker", "exec", LEGIT_CONTAINER, "python", "-c", LEGIT_CLIENT,
        internal_url, victim["username"], PASSWORD, "20",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await asyncio.sleep(0.3)

    results = []
    sem = asyncio.Semaphore(BRUTE_FORCE_CONCURRENCY)
    limits = httpx.Limits(max_connections=BRUTE_FORCE_CONCURRENCY)

    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        async def attempt(i):
            async with sem:
                t = time.perf_counter()
                try:
                    r = await client.post(url, json={"username": victim["username"], "password": f"mala-{i}"})
                    status = r.status_code
                except httpx.HTTPError:
                    status = 0
                results.append((status, (time.perf_counter() - t) * 1000))

        start = time.perf_counter()
        await asyncio.gather(*(attempt(i) for i in range(BRUTE_FORCE_ATTEMPTS)))
        duration = time.perf_counter() - start

    out, _ = await legit.communicate()
    legit_results = json.loads(out.decode() or "[]")

    blocked = [ms for s, ms in results if s == 429]
    reached = [ms for s, ms in results if s == 401]
    other = sorted({s for s, _ in results if s not in (401, 429)})
    legit_ok = sum(1 for s, _ in legit_results if s == 200)
    return {
        "intentos": len(results),
        "duracion_s": round(duration, 2),
        "tasa_ataque_rps": round(len(results) / duration, 1),
        "bloqueados_429": len(blocked),
        "llegaron_a_auth_401": len(reached),
        "otros_estados": other,
        "pct_bloqueado": round(100 * len(blocked) / len(results), 1),
        "maximo_teorico_que_pasa": round(20 + 10 * duration),
        "latencia_429_p50_ms": percentile(blocked, 50),
        "latencia_429_p95_ms": percentile(blocked, 95),
        "latencia_401_p95_ms": percentile(reached, 95),
        "legitimo_intentos": len(legit_results),
        "legitimo_ok": legit_ok,
        "pct_legitimo_ok": round(100 * legit_ok / len(legit_results), 1) if legit_results else None,
        "legitimo_p95_ms": percentile([ms for _, ms in legit_results], 95),
    }


# ----------------------------------------------------------------------------------- S2 acceso interno


def internal_variants(prefix):
    p = prefix
    paths = [
        f"{p}/internal/auth/login", f"{p}/internal/logic/games", f"{p}/internal/profile/users/x/profile",
        f"{p}/internal/tutor/analyses", f"{p}/internal", f"{p}/internal/", f"{p}/internal?x=1",
        f"{p.upper()}/INTERNAL/auth/login", f"{p.title()}/Internal/logic/games", f"{p}/iNtErNaL/auth/login",
        f"{p}//internal/auth/login", f"{p}///internal/logic/games",
        f"{p}/%69nternal/auth/login", f"{p}/%49NTERNAL/logic/games", f"{p}/internal%2Fauth/login",
        f"{p}/%2569nternal/auth/login",
        f"{p}/./internal/auth/login", f"{p}/x/../internal/auth/login", f"{p}/internal/../internal/logic/games",
        f"{p}/ws/../internal/logic/games" if p else "/x/../internal/logic/games",
        f"{p}/internal/auth/login;x=1", f"{p}/internal/auth/login%00",
    ]
    if p:  # en la web, además, sin el prefijo /api (va al frontend, tampoco a un gateway)
        paths += ["/internal/auth/login", "/INTERNAL/logic/games"]
    methods = ["GET", "POST", "PUT", "DELETE"]
    return [(m, path) for path in paths for m in (methods if path.endswith("/internal/auth/login") else ["GET"])]


async def raw_request(port, method, path, extra_headers=""):
    """HTTP/1.1 crudo: la ruta viaja tal cual (httpx normalizaría '..' y '.')."""
    t = time.perf_counter()
    reader, writer = await asyncio.open_connection(HOST, port)
    body = "{}" if method in ("POST", "PUT") else ""
    req = (f"{method} {path} HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n{extra_headers}"
           f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n{body}")
    writer.write(req.encode("latin-1"))
    await writer.drain()
    data = await reader.read()
    writer.close()
    ms = (time.perf_counter() - t) * 1000
    status_line = data.split(b"\r\n", 1)[0].decode("latin-1")
    status = int(status_line.split()[1]) if len(status_line.split()) > 1 else 0
    return status, ms


def gateway_log_hits(since_iso):
    """Líneas de log de los gateways que mencionan 'internal' desde `since_iso` (peticiones que los alcanzaron)."""
    hits = 0
    for name in GATEWAY_CONTAINERS:
        out = subprocess.run(["docker", "logs", "--since", since_iso, name],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        text = (out.stdout or "") + (out.stderr or "")
        hits += sum(1 for line in text.splitlines()
                    if "internal" in line.lower() and ("GET " in line or "POST " in line
                                                       or "PUT " in line or "DELETE " in line))
    return hits


async def internal_access(entry):
    cfg = ENTRIES[entry]
    since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    await asyncio.sleep(1.1)
    variants = internal_variants(cfg["prefix"])
    rows = []
    for method, path in variants:
        status, ms = await raw_request(cfg["port"], method, path, "X-User-Id: 00000000-0000-4000-8000-000000000000\r\n")
        rows.append({"metodo": method, "ruta": path, "estado": status, "ms": round(ms, 1)})
    await asyncio.sleep(1.5)
    hits = gateway_log_hits(since)
    blocked = [r for r in rows if r["estado"] in (400, 404)]
    return {
        "peticiones": len(rows),
        "bloqueadas": len(blocked),
        "pct_bloqueado": round(100 * len(blocked) / len(rows), 1),
        "estados": sorted({r["estado"] for r in rows}),
        "llegaron_a_un_gateway_segun_logs": hits,
        "latencia_p50_ms": percentile([r["ms"] for r in rows], 50),
        "latencia_p95_ms": percentile([r["ms"] for r in rows], 95),
        "detalle": rows,
    }


def port_scan():
    rows = []
    for port, name in SERVICE_PORTS.items():
        s = socket.socket()
        s.settimeout(1)
        try:
            s.connect((HOST, port))
            reachable = True
        except OSError:
            reachable = False
        finally:
            s.close()
        rows.append({"puerto": port, "servicio": name, "alcanzable": reachable})
    return {
        "puertos_probados": len(rows),
        "alcanzables": sum(r["alcanzable"] for r in rows),
        "detalle": rows,
        "publicados_esperados": {"web": WEB_PORT, "movil": MOBILE_PORT},
    }


# ------------------------------------------------------------------------------------- S3 suplantación

SPOOF_HEADERS = ["X-User-Id", "x-user-id", "X-USER-ID", "X_User_Id"]


def spoofing(entry, attacker, victim, victim_game):
    cfg = ENTRIES[entry]
    rows = []
    with httpx.Client(base_url=base(entry), timeout=20) as client:
        for path in cfg["protected"]:
            for header in SPOOF_HEADERS:
                # Con el token del atacante y la identidad de la víctima en la cabecera
                r = client.get(path, headers={"Authorization": f"Bearer {attacker['token']}", header: victim["userId"]})
                leaked = victim["userId"] in r.text or victim["username"] in r.text or victim_game in r.text
                rows.append({"ruta": path, "cabecera": header, "token": "atacante", "estado": r.status_code,
                             "datos_de_la_victima": leaked})
                # Sin token, solo con la cabecera
                r = client.get(path, headers={header: victim["userId"]})
                leaked = victim["userId"] in r.text or victim["username"] in r.text or victim_game in r.text
                rows.append({"ruta": path, "cabecera": header, "token": "ninguno", "estado": r.status_code,
                             "datos_de_la_victima": leaked})
    with_token = [r for r in rows if r["token"] == "atacante"]
    without = [r for r in rows if r["token"] == "ninguno"]
    return {
        "peticiones": len(rows),
        "con_datos_de_la_victima": sum(r["datos_de_la_victima"] for r in rows),
        "pct_fuga": round(100 * sum(r["datos_de_la_victima"] for r in rows) / len(rows), 1),
        "con_token_respuestas_200_propias": sum(1 for r in with_token if r["estado"] == 200 and not r["datos_de_la_victima"]),
        "con_token_total": len(with_token),
        "sin_token_401": sum(1 for r in without if r["estado"] == 401),
        "sin_token_total": len(without),
        "detalle": rows,
    }


# ------------------------------------------------------------------------------------------------ main


async def main():
    print("Creando usuarios (víctima y atacante)...")
    victim = make_user("movil", "victima")
    attacker = make_user("movil", "atacante")
    victim_game = seed_victim_game(victim)
    await asyncio.sleep(4)  # que se vacíe la ráfaga del rate-limit usada por los registros

    results = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proxy": {"web": base("web"), "movil": base("movil")},
        "parametros": {"intentos_fuerza_bruta": BRUTE_FORCE_ATTEMPTS, "concurrencia": BRUTE_FORCE_CONCURRENCY,
                       "limite_nginx": "10 r/s por IP, ráfaga 20 (zona auth_zone compartida por ambas entradas)"},
        "S2_puertos": port_scan(),
    }
    for entry in ENTRIES:
        print(f"[{entry}] S1 fuerza bruta...")
        s1 = await brute_force(entry, victim)
        await asyncio.sleep(5)
        print(f"[{entry}] S2 acceso interno...")
        s2 = await internal_access(entry)
        print(f"[{entry}] S3 suplantación...")
        s3 = spoofing(entry, attacker, victim, victim_game)
        results[entry] = {"S1": s1, "S2": s2, "S3": s3}
        await asyncio.sleep(3)

    out = Path(__file__).with_name("resultados.json")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    for entry in ENTRIES:
        r = results[entry]
        print(f"\n== {entry} ==")
        print(f"S1: {r['S1']['pct_bloqueado']} % bloqueado ({r['S1']['bloqueados_429']}/{r['S1']['intentos']}), "
              f"{r['S1']['llegaron_a_auth_401']} llegaron a Auth (máx. teórico {r['S1']['maximo_teorico_que_pasa']}), "
              f"legítimo {r['S1']['legitimo_ok']}/{r['S1']['legitimo_intentos']}")
        print(f"S2: {r['S2']['pct_bloqueado']} % bloqueado, {r['S2']['llegaron_a_un_gateway_segun_logs']} en logs de gateways, "
              f"p95 {r['S2']['latencia_p95_ms']} ms")
        print(f"S3: {r['S3']['con_datos_de_la_victima']} fugas de {r['S3']['peticiones']}, "
              f"sin token 401: {r['S3']['sin_token_401']}/{r['S3']['sin_token_total']}")
    p = results["S2_puertos"]
    print(f"\nPuertos internos alcanzables desde el host: {p['alcanzables']}/{p['puertos_probados']}")
    print(f"Resultados en {out}")


if __name__ == "__main__":
    asyncio.run(main())
