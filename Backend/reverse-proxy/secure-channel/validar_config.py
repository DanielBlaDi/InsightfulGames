"""Validación ESTÁTICA del Secure Channel (Prototype 3, escenario 1). No necesita Docker.

    pip install crossplane pyyaml
    python Backend/reverse-proxy/secure-channel/validar_config.py

Hace lo que hace la imagen al arrancar (envsubst de las plantillas con NGINX_ENVSUBST_FILTER), arma la
configuración como queda en /etc/nginx/conf.d y la analiza con crossplane (parser de NGINX Inc.) en modo
estricto: directivas conocidas, contexto y número de argumentos. Después comprueba la política TLS y el
compose.yaml. NO sustituye a `nginx -t` (no carga certificados ni módulos): eso lo hace verificar_canal_seguro.py
contra los contenedores.
"""

import re
import sys
import tempfile
from pathlib import Path

import crossplane
import yaml

ROOT = Path(__file__).resolve().parents[3]
NGINX = ROOT / "Backend" / "reverse-proxy" / "nginx"
DOCKERFILE = ROOT / "Backend" / "reverse-proxy" / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("OK   " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""))


def envsubst_filter():
    m = re.search(r'NGINX_ENVSUBST_FILTER="([^"]+)"', DOCKERFILE.read_text(encoding="utf-8"))
    return re.compile(m.group(1))


def render(template, env):
    """Como envsubst con la lista de variables definidas que deja pasar el filtro."""
    flt = envsubst_filter()
    names = [n for n in env if flt.search(n)]

    def sub(m):
        name = m.group(1) or m.group(2)
        return env[name] if name in names else m.group(0)

    return re.sub(r"\$\{(\w+)\}|\$(\w+)", sub, template)


def parse(entry, env):
    tmp = Path(tempfile.mkdtemp())
    (tmp / "conf.d").mkdir()
    (tmp / "conf.d" / "00-common.conf").write_text((NGINX / "common.conf").read_text(encoding="utf-8"), encoding="utf-8")
    rendered = render((NGINX / f"{entry}.conf.template").read_text(encoding="utf-8"), env)
    (tmp / "conf.d" / "default.conf").write_text(rendered, encoding="utf-8")
    # nginx.conf de la imagen (simplificado): http incluye conf.d/*.conf
    (tmp / "nginx.conf").write_text("events {}\nhttp {\n    include conf.d/*.conf;\n}\n", encoding="utf-8")
    return rendered, crossplane.parse(str(tmp / "nginx.conf"), strict=True, check_ctx=True, check_args=True,
                                      comments=False)


def walk(block, path=()):
    for d in block:
        yield d, path
        if "block" in d:
            yield from walk(d["block"], path + (d,))


def directives(payload):
    for f in payload["config"]:
        yield from walk(f["parsed"])


def servers(payload):
    return [d for d, _ in directives(payload) if d["directive"] == "server"]


def find(block, name):
    return [d for d, _ in walk(block) if d["directive"] == name]


ENV = {"PUBLIC_HTTPS_PORT": "8443", "HSTS_MAX_AGE": "0", "HOME": "/", "HOSTNAME": "x"}

for entry, http_port in (("web", "8000"), ("mobile", "8090")):
    print(f"\n== Entrada {entry}")
    rendered, payload = parse(entry, ENV)
    # crossplane en modo estricto toma las entradas de un bloque `map` ("default upgrade;", "'' close;")
    # por directivas: en Nginx son pares clave-valor válidos. Solo se ignoran los errores dentro de un `map`.
    def inside_map(error):
        if not error.get("file") or not error.get("line"):
            return False
        text = Path(error["file"]).read_text(encoding="utf-8").splitlines()
        for start, line in enumerate(text, 1):
            if re.match(r"\s*map\s", line):
                end = next(i for i in range(start, len(text) + 1) if text[i - 1].strip() == "}")
                if start < error["line"] < end:
                    return True
        return False

    all_errors = payload["errors"] + [{**e, "file": f["file"]} for f in payload["config"] for e in f["errors"]]
    errors = list({(e.get("file"), e.get("line"), e["error"]): e for e in all_errors if not inside_map(e)}.values())
    check("crossplane (estricto): sin errores de sintaxis, contexto ni argumentos", not errors,
          "; ".join(e["error"] for e in errors))
    check("envsubst: no quedan ${VAR} sin sustituir", "${" not in rendered)
    check("envsubst: variables de Nginx intactas ($host, $request_uri, $http_upgrade)",
          all(v in rendered for v in ("$http_host", "$remote_addr")) and ("$request_uri" in rendered or entry == "mobile"))

    common = [d for d, p in directives(payload) if not p or p[-1]["directive"] == "http"]
    protos = [d["args"] for d in common if d["directive"] == "ssl_protocols"]
    check("ssl_protocols = TLSv1.2 TLSv1.3 (sin SSLv3/TLSv1/TLSv1.1)", protos == [["TLSv1.2", "TLSv1.3"]], str(protos))
    ciphers = [d["args"][0] for d in common if d["directive"] == "ssl_ciphers"]
    check("cifrados TLS 1.2 solo ECDHE + AEAD", bool(ciphers) and all(
        c.startswith("ECDHE-") and ("GCM" in c or "CHACHA20" in c) for c in ciphers[0].split(":")), ciphers[0] if ciphers else "")
    check("ssl_session_tickets off", any(d["directive"] == "ssl_session_tickets" and d["args"] == ["off"] for d in common))

    srv = servers(payload)
    tls = [s for s in srv if any("ssl" in d["args"] for d in find(s["block"], "listen"))]
    plain = [s for s in srv if s not in tls]
    check("un server HTTPS en :8443 y uno HTTP", len(tls) == 1 and len(plain) == 1
          and find(tls[0]["block"], "listen")[0]["args"] == ["8443", "ssl"]
          and find(plain[0]["block"], "listen")[0]["args"] == [http_port])
    t = tls[0]["block"]
    cert = find(t, "ssl_certificate")
    key = find(t, "ssl_certificate_key")
    check("HTTPS: certificado y clave desde /etc/nginx/certs (montaje de solo lectura)",
          cert and key and cert[0]["args"] == ["/etc/nginx/certs/tls.crt"] and key[0]["args"] == ["/etc/nginx/certs/tls.key"])
    hsts = [d for d in find(t, "add_header") if d["args"][0] == "Strict-Transport-Security"]
    check("HTTPS: cabecera HSTS con 'always'", hsts and hsts[0]["args"][-1] == "always" and "max-age=0" in hsts[0]["args"][1])
    check("HTTP: no reenvía nada a los servicios (sin proxy_pass)", not find(plain[0]["block"], "proxy_pass"))
    health = [d for d in find(plain[0]["block"], "location") if d["args"] == ["=", "/health"]]
    check(f"HTTP :{http_port}: /health para el healthcheck del contenedor", bool(health))
    internal = [d for d in find(t, "location") if "internal" in " ".join(d["args"])]
    check("HTTPS: /internal bloqueado en el borde (404)", internal and any(r["args"][0] == "404" for r in find(internal[0]["block"], "return")))
    check("HTTPS: X-User-Id vaciado en todos los proxy_pass", all(
        any(h["args"][:2] == ["X-User-Id", ""] for h in find(loc["block"], "proxy_set_header"))
        for loc in find(t, "location") if find(loc["block"], "proxy_pass")))
    if entry == "web":
        redirect = [r for r in find(plain[0]["block"], "return") if r["args"][0] == "308"]
        check("HTTP: páginas -> 308 a https://$host:<puerto>$request_uri",
              redirect and redirect[0]["args"][1] == "https://$host:8443$request_uri")
        api = [d for d in find(plain[0]["block"], "location") if d["args"] == ["/api/"]]
        check("HTTP: /api/* -> 403 HTTPS_REQUIRED (no se redirige ni se reenvía)",
              api and find(api[0]["block"], "return")[0]["args"][0] == "403")
        ws = [d for d in find(t, "location") if d["args"] == ["/api/ws/"]]
        hdr = {h["args"][0]: h["args"][1] for h in find(ws[0]["block"], "proxy_set_header")} if ws else {}
        check("WSS: Upgrade/Connection y HTTP/1.1 hacia el gateway",
              hdr.get("Upgrade") == "$http_upgrade" and hdr.get("Connection") == "$connection_upgrade"
              and find(ws[0]["block"], "proxy_http_version")[0]["args"] == ["1.1"])
        check("X-Forwarded-Proto = $scheme (https detrás del proxy)", all(
            h["args"][1] == "$scheme" for h in find(t, "proxy_set_header") if h["args"][0] == "X-Forwarded-Proto"))
    else:
        rest = [d for d in find(plain[0]["block"], "location") if d["args"] == ["/"]]
        check("HTTP móvil: todo salvo /health -> 403 HTTPS_REQUIRED",
              rest and find(rest[0]["block"], "return")[0]["args"][0] == "403")

print("\n== compose.yaml")
compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
svc = compose["services"]
published = {n: v.get("ports") for n, v in svc.items() if v.get("ports")}
check("solo los dos reverse proxies publican puertos", set(published) == {"reverse-proxy-web", "reverse-proxy-mobile"}, str(set(published)))
check("web publica HTTP (redirección) y HTTPS", published.get("reverse-proxy-web") == ["${FRONTEND_PORT:?}:8000", "${FRONTEND_HTTPS_PORT:?}:8443"])
check("móvil publica solo HTTPS", published.get("reverse-proxy-mobile") == ["${MOBILE_HTTPS_PORT:?}:8443"])
for name, var in (("reverse-proxy-web", "WEB_TLS_DIR"), ("reverse-proxy-mobile", "MOBILE_TLS_DIR")):
    vols = svc[name].get("volumes", [])
    ok = len(vols) == 1 and vols[0]["source"] == "${%s:?}" % var and vols[0]["target"] == "/etc/nginx/certs" \
        and vols[0]["read_only"] is True and vols[0]["bind"]["create_host_path"] is False
    check(f"{name}: certificados montados en solo lectura, sin crear la ruta", ok)
nets = compose["networks"]
check("redes conservadas (10.20.1/2/3.0/24; private_* internas)",
      [nets[n]["ipam"]["config"][0]["subnet"] for n in ("public_network", "private_api", "private_back")]
      == ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
      and nets["private_api"].get("internal") and nets["private_back"].get("internal") and not nets["public_network"].get("internal"))
check("IP fijas de los proxies conservadas",
      svc["reverse-proxy-web"]["networks"] == {"public_network": {"ipv4_address": "10.20.1.11"}, "private_api": {"ipv4_address": "10.20.2.10"}}
      and svc["reverse-proxy-mobile"]["networks"] == {"public_network": {"ipv4_address": "10.20.1.12"}, "private_api": {"ipv4_address": "10.20.2.11"}})
gw = svc["api-gateway-component"]["environment"]
check("gateway web: COOKIE_SECURE y WS_ALLOWED_ORIGINS desde .env", gw["COOKIE_SECURE"] == "${COOKIE_SECURE:?}" and gw["WS_ALLOWED_ORIGINS"] == "${WS_ALLOWED_ORIGINS:?}")
check("WAF sigue comentado (no se habilita)", "waf-component" not in svc)

ok = sum(results)
print(f"\n{ok}/{len(results)} comprobaciones estáticas superadas")
sys.exit(0 if ok == len(results) else 1)
