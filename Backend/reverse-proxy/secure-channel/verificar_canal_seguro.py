"""Verificación del Secure Channel (Prototype 3, escenario 1) contra el stack en Docker.

    pip install websockets
    $env:TLS_CA_FILE = "$(mkcert -CAROOT)\\rootCA.pem"     # CA que firmó el certificado (nunca la clave)
    python Backend/reverse-proxy/secure-channel/verificar_canal_seguro.py

Variables: PROXY_HOST (localhost), FRONTEND_PORT, FRONTEND_HTTPS_PORT, MOBILE_HTTPS_PORT, TLS_CA_FILE.
Todas las conexiones TLS VALIDAN el certificado con TLS_CA_FILE y el nombre del host: ninguna prueba desactiva
la verificación. Escribe resultados-canal-seguro.json junto a este archivo (evidencia para el informe).
"""

import asyncio
import http.client
import json
import os
import socket
import ssl
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import websockets

HOST = os.getenv("PROXY_HOST", "localhost")
HTTP_PORT = int(os.getenv("FRONTEND_PORT", "8080"))
HTTPS_PORT = int(os.getenv("FRONTEND_HTTPS_PORT", "8443"))
MOBILE_PORT = int(os.getenv("MOBILE_HTTPS_PORT", "8444"))
CA_FILE = os.getenv("TLS_CA_FILE", "")
ORIGIN = f"https://{HOST}" if HTTPS_PORT == 443 else f"https://{HOST}:{HTTPS_PORT}"
PASSWORD = "Clave-Segura-123"

# Puertos que NO deben responder en el host (servicios internos y el HTTP del proxy móvil)
INTERNAL_PORTS = {8000: "nginx web (interno)", 8090: "nginx móvil HTTP", 8091: "gateway móvil (debug)",
                  8080: "api-gateway web", 8081: "auth", 8082: "game-logic", 8083: "single-player",
                  8084: "multiplayer", 8085: "tutor", 8086: "botcito", 8087: "profile-stats",
                  27017: "mongo", 3306: "mysql", 5432: "postgres", 5672: "rabbitmq", 15672: "rabbitmq admin"}

results = []


def check(group, name, ok, detail=""):
    results.append({"grupo": group, "prueba": name, "ok": bool(ok), "detalle": str(detail)[:300]})
    print(("OK   " if ok else "FAIL ") + f"[{group}] {name}" + (f" — {detail}" if detail else ""))


def trusted_ctx(min_v=None, max_v=None):
    """Cliente que confía SOLO en la CA indicada y comprueba el nombre del host."""
    ctx = ssl.create_default_context(cafile=CA_FILE)
    if min_v:
        ctx.minimum_version = min_v
    if max_v:
        ctx.maximum_version = max_v
    return ctx


def https(port, method, path, body=None, headers=None, ctx=None, host=HOST):
    conn = http.client.HTTPSConnection(host, port, context=ctx or trusted_ctx(), timeout=15)
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    h.update(headers or {})
    conn.request(method, path, body=data, headers=h)
    version = conn.sock.version()
    r = conn.getresponse()
    out = (r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace"), version)
    conn.close()
    return out


def http_plain(port, path):
    conn = http.client.HTTPConnection(HOST, port, timeout=10)
    conn.request("GET", path)
    r = conn.getresponse()
    out = (r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace"))
    conn.close()
    return out


def handshake(port, ctx, server_hostname=HOST):
    """Devuelve (True, versión) si el handshake TLS completa; (False, error) si el servidor o la validación lo rechazan."""
    try:
        with socket.create_connection((HOST, port), timeout=10) as raw:
            with ctx.wrap_socket(raw, server_hostname=server_hostname) as s:
                return True, s.version()
    except (ssl.SSLError, ssl.CertificateError, ConnectionResetError, OSError) as e:
        return False, f"{type(e).__name__}: {e}"


def legacy_ctx(version):
    """Cliente que OFRECE solo TLS 1.0 o 1.1 (y lo permite en su propio lado), para que el rechazo sea del servidor."""
    ctx = trusted_ctx()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    ctx.minimum_version = version
    ctx.maximum_version = version
    return ctx


def tls_checks(label, port):
    ok, v = handshake(port, trusted_ctx())
    check(label, "HTTPS con certificado confiable (CA de desarrollo, nombre verificado)", ok, v)
    for name, version in (("TLS 1.2", ssl.TLSVersion.TLSv1_2), ("TLS 1.3", ssl.TLSVersion.TLSv1_3)):
        ok, v = handshake(port, trusted_ctx(version, version))
        check(label, f"{name} aceptado", ok and v == name.replace(" ", "v"), v)
    for name, version in (("TLS 1.0", ssl.TLSVersion.TLSv1), ("TLS 1.1", ssl.TLSVersion.TLSv1_1)):
        ok, v = handshake(port, legacy_ctx(version))
        check(label, f"{name} rechazado por el servidor", not ok, v)
    empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # verificación activa, sin ninguna CA de confianza
    ok, v = handshake(port, empty)
    check(label, "cliente sin la CA: certificado no confiable -> rechazado", not ok and "CERTIFICATE_VERIFY_FAILED" in v, v)
    ok, v = handshake(port, trusted_ctx(), server_hostname="otro-dominio.example")
    check(label, "nombre de host que no está en el certificado -> rechazado", not ok and "CERTIFICATE_VERIFY_FAILED" in v, v)


def main():
    if not CA_FILE or not Path(CA_FILE).is_file():
        print("Define TLS_CA_FILE con el certificado de la CA (p. ej. \"$(mkcert -CAROOT)\\rootCA.pem\").")
        sys.exit(2)

    # ------------------------------------------------------------------ web: TLS
    tls_checks("web TLS", HTTPS_PORT)
    status, headers, _, _ = https(HTTPS_PORT, "GET", "/health")
    hsts = headers.get("Strict-Transport-Security", "")
    check("web TLS", "HSTS presente en HTTPS", status == 200 and hsts.startswith("max-age="), hsts)

    # ------------------------------------------------------------------ web: HTTP en claro
    status, headers, _ = http_plain(HTTP_PORT, "/health")
    check("web HTTP", "/health por HTTP (healthcheck) responde 200", status == 200)
    status, headers, _ = http_plain(HTTP_PORT, "/estadisticas?x=1")
    loc = headers.get("Location", "")
    check("web HTTP", "páginas por HTTP -> 308 a HTTPS conservando ruta y consulta",
          status == 308 and loc == f"https://{HOST}:{HTTPS_PORT}/estadisticas?x=1", f"{status} {loc}")
    for path in ("/api/stats/me", "/api/auth/login", "/api/internal/auth/login"):
        status, _, body = http_plain(HTTP_PORT, path)
        check("web HTTP", f"{path} por HTTP -> 403 HTTPS_REQUIRED (no llega al gateway)",
              status == 403 and "HTTPS_REQUIRED" in body, status)

    # ------------------------------------------------------------------ web: REST y cookie
    user = "tls_" + uuid.uuid4().hex[:8]
    status, _, body, version = https(HTTPS_PORT, "POST", "/api/auth/register", {"username": user, "password": PASSWORD})
    check("web REST", f"registro por HTTPS ({version})", status in (200, 201), status)
    status, headers, body, _ = https(HTTPS_PORT, "POST", "/api/auth/login", {"username": user, "password": PASSWORD})
    cookie = headers.get("Set-Cookie", "")
    attrs = [a.strip().lower() for a in cookie.split(";")]
    check("web REST", "login por HTTPS", status == 200, status)
    check("sesión", "cookie session con Secure, HttpOnly y SameSite=Lax",
          "secure" in attrs and "httponly" in attrs and "samesite=lax" in attrs, "; ".join(attrs[1:]))
    session = cookie.split(";")[0]
    status, _, body, _ = https(HTTPS_PORT, "GET", "/api/stats/me", headers={"Cookie": session})
    check("web REST", "petición autenticada por HTTPS (/api/stats/me)", status == 200, status)

    # ------------------------------------------------------------------ web: WSS
    status, _, body, _ = https(HTTPS_PORT, "POST", "/api/games", {"mode": "local"}, headers={"Cookie": session})
    game_id = json.loads(body).get("gameId") if status in (200, 201) else None
    check("web WSS", "crear partida local por HTTPS", game_id, status)

    async def wss(origin):
        url = f"wss://{HOST}:{HTTPS_PORT}/api/ws/games/{game_id}"
        try:
            async with websockets.connect(url, ssl=trusted_ctx(), origin=origin,
                                          extra_headers={"Cookie": session}, open_timeout=15) as ws:
                return "ok", json.loads(await asyncio.wait_for(ws.recv(), 15))
        except websockets.ConnectionClosed as e:
            return "cerrado", e.rcvd.code if e.rcvd else None
        except Exception as e:  # noqa: BLE001
            return "error", f"{type(e).__name__}: {e}"

    if game_id:
        res = asyncio.run(wss(ORIGIN))
        check("web WSS", "partida por WSS: el primer mensaje es el state", res[0] == "ok" and res[1].get("type") == "state", str(res)[:120])
        res = asyncio.run(wss(f"http://{HOST}:{HTTP_PORT}"))
        check("web WSS", "WSS desde un origen http:// -> 4403", res == ("cerrado", 4403), res)

    # ------------------------------------------------------------------ borde: rutas internas
    for path in ("/api/internal/auth/login", "/API/Internal/logic/games", "/api//internal/x", "/api/%69nternal/x"):
        status, _, _, _ = https(HTTPS_PORT, "GET", path)
        check("borde", f"{path} por HTTPS -> 404", status == 404, status)

    # ------------------------------------------------------------------ móvil
    tls_checks("móvil TLS", MOBILE_PORT)
    status, _, body, version = https(MOBILE_PORT, "POST", "/auth/login", {"username": user, "password": PASSWORD})
    check("móvil REST", f"login de la app por HTTPS ({version})", status == 200 and "accessToken" in body, status)
    status, _, _, _ = https(MOBILE_PORT, "GET", "/internal/auth/login")
    check("borde", "móvil /internal por HTTPS -> 404", status == 404, status)

    # ------------------------------------------------------------------ exposición de puertos
    for port, name in INTERNAL_PORTS.items():
        if port in (HTTP_PORT, HTTPS_PORT, MOBILE_PORT):
            continue
        with socket.socket() as s:
            s.settimeout(1)
            reachable = s.connect_ex((HOST if HOST != "localhost" else "127.0.0.1", port)) == 0
        check("puertos", f"{port} ({name}) no publicado en el host", not reachable)

    ok = sum(r["ok"] for r in results)
    print(f"\n{ok}/{len(results)} comprobaciones superadas")
    out = Path(__file__).with_name("resultados-canal-seguro.json")
    out.write_text(json.dumps({
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": HOST, "puertos": {"http_web": HTTP_PORT, "https_web": HTTPS_PORT, "https_movil": MOBILE_PORT},
        "openssl_cliente": ssl.OPENSSL_VERSION, "superadas": ok, "total": len(results), "resultados": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidencia: {out}")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
