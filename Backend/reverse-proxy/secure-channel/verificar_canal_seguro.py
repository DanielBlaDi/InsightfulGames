"""Verificación del Secure Channel (Prototype 3, escenario 1) contra el stack en Docker.

    pip install websockets
    $env:TLS_CA_FILE = "$(mkcert -CAROOT)\\rootCA.pem"     # CA que firmó el certificado PÚBLICO (nunca la clave)

    # Despliegue integrado: docker compose up --build -d
    python Backend/reverse-proxy/secure-channel/verificar_canal_seguro.py --modo waf

    python Backend/reverse-proxy/secure-channel/verificar_canal_seguro.py --modo waf --control-negativo-upstream

Variables: PROXY_HOST (localhost), FRONTEND_PORT, FRONTEND_HTTPS_PORT, MOBILE_HTTPS_PORT, TLS_CA_FILE y, para el
control negativo, EDGE_TLS_DIR e INTERNAL_NEGATIVE_TLS_DIR (certs/internal/negative-wrong-name).
Todas las conexiones TLS VALIDAN el certificado y el nombre del host: ninguna prueba desactiva la verificación.
Escribe resultados-canal-seguro-<modo>.json junto a este archivo (evidencia para el informe).

--control-negativo-upstream RECREA reverse-proxy-web dos veces con un certificado incorrecto (otra CA; CA interna
con otro nombre), comprueba que el WAF responde 502 y lo deja como estaba. Solo para el entorno de pruebas.
"""

import argparse
import asyncio
import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[3]
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

WAF_LAYERS = ["compose.yaml"]  # despliegue integrado (WAF + Secure Channel)

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
    # r.msg (HTTPMessage) busca cabeceras sin distinguir mayúsculas: el gateway envía "set-cookie" en minúsculas
    out = (r.status, r.msg, r.read().decode("utf-8", "replace"), version)
    conn.close()
    return out


def http_plain(port, path, method="GET", body=None):
    conn = http.client.HTTPConnection(HOST, port, timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
    r = conn.getresponse()
    out = (r.status, r.msg, r.read().decode("utf-8", "replace"))
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


# ------------------------------------------------------------------------------------- Docker (modo waf)
def docker(*args, env=None, timeout=120):
    r = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, timeout=timeout, cwd=ROOT)
    return r.returncode, (r.stdout + r.stderr).strip()


def compose(*args, env=None):
    files = [a for f in WAF_LAYERS for a in ("-f", f)]
    return docker("compose", *files, *args, env=env, timeout=600)


def logs_since(container, since):
    return docker("logs", "--since", since, container)[1]


def wait_healthy(container, seconds=120):
    end = time.time() + seconds
    while time.time() < end:
        _, status = docker("inspect", "-f", "{{.State.Health.Status}}", container)
        if status == "healthy":
            return True
        time.sleep(2)
    return False


def is_waf_block(status, body):
    return status == 403 and "<html" in body.lower()


def published_ports():
    """{contenedor: {puertos del host}} según docker ps."""
    _, out = docker("ps", "--format", "{{.Names}}\t{{.Ports}}")
    ports = {}
    for line in out.splitlines():
        name, _, desc = line.partition("\t")
        found = {int(p) for p in re.findall(r"(?:0\.0\.0\.0|\[::\]|127\.0\.0\.1):(\d+)->", desc)}
        if found:
            ports[name] = found
    return ports


def waf_checks(session):
    print("\n== Tramo WAF -> Reverse Proxy (dentro de Docker)")
    for waf, proxy in (("waf-web", "reverse-proxy-web"), ("waf-mobile", "reverse-proxy-mobile")):
        g = f"{waf}->{proxy}"
        rc, conf = docker("exec", waf, "nginx", "-T")
        check(g, "nginx -T del WAF: configuración válida", rc == 0 and "test is successful" in conf, conf[-160:] if rc else "")
        need = {f"proxy_pass https://{proxy}:8443;": "BACKEND por HTTPS",
                "proxy_ssl_verify on;": "verificación del certificado",
                "proxy_ssl_server_name on;": "SNI",
                "proxy_ssl_trusted_certificate /etc/nginx/upstream-ca/ca.crt;": "solo la CA interna",
                "proxy_ssl_protocols TLSv1.2 TLSv1.3;": "TLS 1.2/1.3 hacia el proxy",
                "ssl_protocols TLSv1.2 TLSv1.3;": "TLS 1.2/1.3 hacia el cliente",
                "ssl_certificate /etc/nginx/edge-certs/tls.crt;": "certificado público montado"}
        flat = re.sub(r"\s+", " ", conf)
        missing = [desc for line, desc in need.items() if line not in flat]
        check(g, "configuración efectiva: " + ", ".join(need.values()), not missing, f"falta: {missing}")
        check(g, "sin mTLS (no hay proxy_ssl_certificate)", "proxy_ssl_certificate " not in flat)
        check(g, "ModSecurity activo con OWASP CRS", "modsecurity on;" in flat.lower(), "")
        rc, out = docker("exec", waf, "curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{ssl_verify_result}",
                         "--cacert", "/etc/nginx/upstream-ca/ca.crt", f"https://{proxy}:8443/health")
        check(g, f"desde el WAF: https://{proxy}:8443 validado con la CA interna (200, verify 0)", rc == 0 and out == "200 0", out)
        rc, out = docker("exec", waf, "curl", "-sS", "-o", "/dev/null", f"https://{proxy}:8443/health")
        check(g, "la CA interna NO está en el almacén del sistema del WAF (curl sin --cacert falla)", rc != 0, out[-120:])
        for target in ("api-gateway-component", "api-gateway-mobile", "frontend-component", "auth-component", "mongo-db"):
            rc, _ = docker("exec", waf, "getent", "hosts", target)
            check(g, f"segmentación: el WAF no resuelve {target}", rc != 0)

    print("\n== Red public_network y puertos publicados")
    _, net = docker("inspect", "-f",
                    "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{end}}", "waf-web")
    _, members = docker("network", "inspect", net, "-f", "{{range .Containers}}{{.Name}} {{end}}")
    check("red", f"{net}: solo los 2 WAF y los 2 proxies", sorted(members.split()) ==
          ["reverse-proxy-mobile", "reverse-proxy-web", "waf-mobile", "waf-web"], members)
    _, gw_ips = docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", "api-gateway-component")
    for ip in gw_ips.split():
        rc, _ = docker("exec", "waf-web", "curl", "-sS", "-m", "3", f"http://{ip}:8080/health")
        check("red", f"el WAF no alcanza el gateway web por IP ({ip})", rc != 0)
    pub = published_ports()
    expected = {"waf-web": {HTTP_PORT, HTTPS_PORT}, "waf-mobile": {MOBILE_PORT}}
    check("puertos", "solo los WAF publican puertos (HTTP web solo redirige; móvil solo HTTPS)", pub == expected, pub)

    print("\n== HTTP público del WAF: nunca se reenvía")
    probe = uuid.uuid4().hex
    since = datetime.now(timezone.utc).isoformat()
    status, headers, _ = http_plain(HTTP_PORT, f"/estadisticas?x={probe}")
    loc = headers.get("Location", "")
    check("waf HTTP", "páginas por HTTP -> 301 a HTTPS conservando ruta y consulta",
          status == 301 and loc == f"https://{HOST}:{HTTPS_PORT}/estadisticas?x={probe}", f"{status} {loc}")
    status, headers, _ = http_plain(HTTP_PORT, f"/api/auth/login?probe={probe}", "POST", {"username": "x", "password": "y"})
    check("waf HTTP", "POST /api/auth/login por HTTP -> 301 (no se procesa)", status == 301, status)
    time.sleep(1)
    leaked = [c for c in ("reverse-proxy-web", "api-gateway-component") if probe in logs_since(c, since)]
    check("waf HTTP", "ninguna petición HTTP llegó al proxy ni al gateway", not leaked, leaked)

    print("\n== ModSecurity / OWASP CRS sobre HTTPS")
    since = datetime.now(timezone.utc).isoformat()
    status, _, body, _ = https(HTTPS_PORT, "GET", "/api/stats/me?id=1%27%20OR%20%271%27%3D%271")
    check("waf reglas", "inyección SQL en la consulta -> 403 del WAF", is_waf_block(status, body), status)
    status, _, body, _ = https(HTTPS_PORT, "GET", "/?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    check("waf reglas", "XSS en la consulta -> 403 del WAF", is_waf_block(status, body), status)
    status, _, body, _ = https(MOBILE_PORT, "GET", "/profile/me?id=1%27%20UNION%20SELECT%20password%20FROM%20users--")
    check("waf reglas", "móvil: inyección SQL -> 403 del WAF", is_waf_block(status, body), status)
    status, _, body, _ = https(HTTPS_PORT, "PUT", "/api/games", {"mode": "local"}, headers={"Cookie": session})
    check("waf reglas", "método no permitido (PUT) sigue bloqueado por CRS (911100)", is_waf_block(status, body), status)
    time.sleep(1)
    audit = logs_since("waf-web", since)
    check("waf reglas", "el audit log del WAF registra las reglas CRS (942xxx / 941xxx)",
          re.search(r'"942\d{3}"|id "942\d{3}"|942\d{3}', audit) and re.search(r"941\d{3}", audit))

    print("\n== IP real: no se puede falsificar desde fuera")
    probe = uuid.uuid4().hex
    since = datetime.now(timezone.utc).isoformat()
    # /health no se registra (access_log off): la sonda va a una ruta que el proxy sí registra (404 de /api/internal)
    https(HTTPS_PORT, "GET", f"/api/internal/{probe}", headers={"X-Real-IP": "203.0.113.77", "X-Forwarded-For": "203.0.113.77"})
    time.sleep(1)
    line = next((l for l in logs_since("reverse-proxy-web", since).splitlines() if probe in l), "")
    client = line.split(" ", 1)[0] if line else ""
    check("ip real", "el proxy registra la IP que vio el WAF, no la cabecera del cliente",
          line and client != "203.0.113.77" and client != "10.20.1.13", client or "sin línea en el log")


def upstream_negative_control():
    print("\n== Control negativo: el WAF rechaza un proxy con certificado incorrecto (recrea reverse-proxy-web)")
    edge = os.getenv("EDGE_TLS_DIR", "./certs/edge")
    wrong = os.getenv("INTERNAL_NEGATIVE_TLS_DIR", "./certs/internal/negative-wrong-name")
    cases = (("certificado de otra CA (el público de mkcert)", edge),
             ("CA interna pero nombre 'otro-servicio'", wrong))
    try:
        for desc, cert_dir in cases:
            if not (ROOT / cert_dir / "tls.crt").is_file() and not Path(cert_dir, "tls.crt").is_file():
                check("negativo", desc, False, f"no existe {cert_dir}/tls.crt (generar_certs_internos.py --control-negativo)")
                continue
            env = {**os.environ, "INTERNAL_WEB_TLS_DIR": cert_dir}
            rc, out = compose("up", "-d", "--no-deps", "--force-recreate", "reverse-proxy-web", env=env)
            healthy = rc == 0 and wait_healthy("reverse-proxy-web")
            since = datetime.now(timezone.utc).isoformat()
            status, _, _, _ = https(HTTPS_PORT, "GET", "/health")
            time.sleep(1)
            log = logs_since("waf-web", since)
            check("negativo", f"{desc} -> el WAF no conecta (502) y registra el fallo de verificación",
                  healthy and status == 502 and re.search(r"upstream SSL certificate verify error|certificate verify failed", log),
                  f"status {status}; " + (re.search(r"upstream SSL[^\n]{0,120}", log) or re.search(r"verify[^\n]{0,80}", log) or ["-"])[0])
    finally:
        rc, out = compose("up", "-d", "--no-deps", "--force-recreate", "reverse-proxy-web")
        ok = rc == 0 and wait_healthy("reverse-proxy-web")
        status = https(HTTPS_PORT, "GET", "/health")[0] if ok else None
        check("negativo", "restaurado: reverse-proxy-web con su certificado interno -> 200 a través del WAF", status == 200, status)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", choices=("waf",), default="waf")
    ap.add_argument("--control-negativo-upstream", action="store_true")
    args = ap.parse_args()
    if not CA_FILE or not Path(CA_FILE).is_file():
        print("Define TLS_CA_FILE con el certificado de la CA (p. ej. \"$(mkcert -CAROOT)\\rootCA.pem\").")
        sys.exit(2)
    entry = "WAF web"

    # ------------------------------------------------------------------ web: TLS cliente -> entrada pública
    tls_checks(f"{entry} TLS", HTTPS_PORT)
    status, headers, _, _ = https(HTTPS_PORT, "GET", "/health")
    hsts = headers.get("Strict-Transport-Security", "")
    check(f"{entry} TLS", "HSTS presente en HTTPS", status == 200 and hsts.startswith("max-age="), hsts)

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

    # ------------------------------------------------------------------ métodos PATCH y DELETE (no los bloquea el WAF)
    if game_id:
        # Partida local: la rendición indica el color que se rinde; el PATCH exige la versión actual (expectedVersion)
        status, _, body, _ = https(HTTPS_PORT, "POST", f"/api/games/{game_id}/resign", {"side": "white"},
                                   headers={"Cookie": session})
        try:
            version = json.loads(body).get("version")
        except ValueError:
            version = None
        status, _, body, _ = https(HTTPS_PORT, "PATCH", f"/api/games/{game_id}/visibility",
                                   {"visibility": "shared", "expectedVersion": version}, headers={"Cookie": session})
        check("métodos", "PATCH /api/games/{id}/visibility (partida terminada) -> 2xx", 200 <= status < 300,
              f"{status} {'(bloqueado por el WAF)' if is_waf_block(status, body) else body[:80]}")
    other = "tls_del_" + uuid.uuid4().hex[:8]
    https(HTTPS_PORT, "POST", "/api/auth/register", {"username": other, "password": PASSWORD})
    _, h, _, _ = https(HTTPS_PORT, "POST", "/api/auth/login", {"username": other, "password": PASSWORD})
    status, _, body, _ = https(HTTPS_PORT, "DELETE", "/api/auth/account",
                               headers={"Cookie": h.get("Set-Cookie", "").split(";")[0]})
    check("métodos", "DELETE /api/auth/account (usuario de prueba) -> 204", status == 204,
          f"{status} {'(bloqueado por el WAF)' if is_waf_block(status, body) else body[:80]}")

    # ------------------------------------------------------------------ borde: rutas internas
    for path in ("/api/internal/auth/login", "/API/Internal/logic/games", "/api//internal/x", "/api/%69nternal/x"):
        status, _, body, _ = https(HTTPS_PORT, "GET", path)
        # Con WAF, CRS puede bloquear antes (403); lo exigido es que no se sirva (nunca 2xx/3xx)
        check("borde", f"{path} por HTTPS -> 404 o 403 del WAF",
              status == 404 or is_waf_block(status, body), status)

    # ------------------------------------------------------------------ móvil
    tls_checks("WAF móvil TLS", MOBILE_PORT)
    status, _, body, version = https(MOBILE_PORT, "POST", "/auth/login", {"username": user, "password": PASSWORD})
    check("móvil REST", f"login de la app por HTTPS ({version})", status == 200 and "accessToken" in body, status)
    status, _, body, _ = https(MOBILE_PORT, "GET", "/internal/auth/login")
    check("borde", "móvil /internal por HTTPS -> 404", status == 404 or is_waf_block(status, body), status)
    mob = "tls_mdel_" + uuid.uuid4().hex[:8]
    https(MOBILE_PORT, "POST", "/auth/register", {"username": mob, "password": PASSWORD})
    _, _, body, _ = https(MOBILE_PORT, "POST", "/auth/login", {"username": mob, "password": PASSWORD})
    token = json.loads(body).get("accessToken", "") if body.startswith("{") else ""
    status, _, body, _ = https(MOBILE_PORT, "DELETE", "/auth/account", headers={"Authorization": f"Bearer {token}"})
    check("métodos", "móvil DELETE /auth/account (usuario de prueba) -> 204", status == 204,
          f"{status} {'(bloqueado por el WAF)' if is_waf_block(status, body) else body[:80]}")

    # ------------------------------------------------------------------ exposición de puertos
    for port, name in INTERNAL_PORTS.items():
        if port in (HTTP_PORT, HTTPS_PORT, MOBILE_PORT):
            continue
        with socket.socket() as s:
            s.settimeout(1)
            reachable = s.connect_ex((HOST if HOST != "localhost" else "127.0.0.1", port)) == 0
        check("puertos", f"{port} ({name}) no publicado en el host", not reachable)

    waf_checks(session)
    if args.control_negativo_upstream:
        upstream_negative_control()

    ok = sum(r["ok"] for r in results)
    print(f"\n[{args.modo}] {ok}/{len(results)} comprobaciones superadas")
    out = Path(__file__).with_name(f"resultados-canal-seguro-{args.modo}.json")
    out.write_text(json.dumps({
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "modo": args.modo,
        "compose": WAF_LAYERS,
        "host": HOST, "puertos": {"http_web": HTTP_PORT, "https_web": HTTPS_PORT, "https_movil": MOBILE_PORT},
        "openssl_cliente": ssl.OPENSSL_VERSION, "superadas": ok, "total": len(results), "resultados": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidencia: {out}")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
