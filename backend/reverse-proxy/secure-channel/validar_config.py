"""Validación ESTÁTICA del Secure Channel y del WAF (Prototype 3, escenario 1). No necesita Docker.

    pip install crossplane pyyaml
    python Backend/reverse-proxy/secure-channel/validar_config.py

Hace lo que hace la imagen al arrancar (envsubst de las plantillas con NGINX_ENVSUBST_FILTER), arma la
configuración como queda en /etc/nginx/conf.d y la analiza con crossplane (parser de NGINX Inc.) en modo
estricto: directivas conocidas, contexto y número de argumentos. Después comprueba la política TLS y el
compose.yaml. NO sustituye a `nginx -t` (no carga certificados ni módulos): eso lo hace verificar_canal_seguro.py
contra los contenedores.

Un solo despliegue: compose.yaml define los dos WAF (waf-web, waf-mobile) delante de los dos reverse proxies.
Solo los WAF publican puertos; los proxies presentan el certificado interno y leen la IP real que envía el WAF.
Comprueba las variables del WAF contra las que define la imagen owasp/modsecurity-crs:nginx.
"""

import subprocess
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
WAF_DIR = ROOT / "Backend" / "waf"

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
    # como directivas: en Nginx son pares clave-valor válidos. Solo se ignoran los errores dentro de un `map`.
    def inside_map(error):
        if not error.get("file") or not error.get("line"):
            return False
        text = Path(error["file"]).read_text(encoding="utf-8").splitlines()
        for start, line in enumerate(text, 1):
            if re.match(r"\s*map\s", line):
                end = next((i for i in range(start, len(text) + 1) if text[i - 1].strip() == "}"), None)
                if end is not None and start < error["line"] < end:
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

print("\n== compose.yaml: entradas públicas")
compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8-sig"))
svc = compose["services"]
published = {n: v.get("ports") for n, v in svc.items() if v.get("ports")}
check("solo los dos WAF publican puertos (proxies y servicios internos, ninguno)",
      set(published) == {"waf-web", "waf-mobile"}, str(set(published)))
check("waf-web: HTTP (solo 301) y HTTPS",
      published.get("waf-web") == ["${FRONTEND_PORT:?}:8080", "${FRONTEND_HTTPS_PORT:?}:8443"], str(published.get("waf-web")))
check("waf-mobile: solo HTTPS (el HTTP móvil no se publica)",
      published.get("waf-mobile") == ["${MOBILE_HTTPS_PORT:?}:8443"], str(published.get("waf-mobile")))
leftovers = sorted(p.name for p in WAF_DIR.glob("compose.waf*.yaml"))
check("sin capas de Compose del WAF aparte (todo está en compose.yaml)", not leftovers, str(leftovers))


def as_mapping(value):
    """depends_on / environment en forma de lista -> mapa (como normaliza Compose)."""
    if isinstance(value, list):
        out = {}
        for item in value:
            k, _, v = str(item).partition("=")
            out[k] = v if "=" in str(item) else {"condition": "service_started"}
        return out
    return value or {}


# Variables que define la imagen owasp/modsecurity-crs:nginx (nginx/Dockerfile y configure-rules.v4.conf
# de coreruleset/modsecurity-crs-docker). Una variable fuera de esta lista sería un error tipográfico que
# la imagen ignoraría en silencio.
WAF_IMAGE_VARS = {
    "BACKEND", "PORT", "SSL_PORT", "SSL_CERT_FILE", "SSL_CERT_KEY_FILE", "SSL_PROTOCOLS", "SSL_CIPHERS",
    "SSL_PREFER_CIPHERS", "SSL_DH_BITS", "SSL_OCSP_STAPLING", "SSL_REDIRECT_PORT", "NGINX_ALWAYS_TLS_REDIRECT",
    "PROXY_SSL", "PROXY_SSL_VERIFY", "PROXY_SSL_VERIFY_DEPTH", "PROXY_SSL_SERVER_NAME", "PROXY_SSL_PROTOCOLS",
    "PROXY_SSL_CIPHERS", "PROXY_SSL_CA_CERT_FILE", "PROXY_SSL_CERT_FILE", "PROXY_SSL_CERT_KEY_FILE",
    "MODSEC_RULE_ENGINE", "MODSEC_AUDIT_ENGINE", "MODSEC_AUDIT_LOG", "ALLOWED_METHODS", "BLOCKING_PARANOIA",
    "ANOMALY_INBOUND", "ANOMALY_OUTBOUND", "REAL_IP_HEADER", "REAL_IP_PROXY_HEADER", "SET_REAL_IP_FROM",
}
AEAD = re.compile(r"^ECDHE-(ECDSA|RSA)-(AES(128|256)-GCM-SHA(256|384)|CHACHA20-POLY1305)$")
PROXY_NETS = {"reverse-proxy-web": {"public_network": "10.20.1.11", "private_api": "10.20.2.10"},
              "reverse-proxy-mobile": {"public_network": "10.20.1.12", "private_api": "10.20.2.11"}}
WAF_IPS = {"waf-web": "10.20.1.13", "waf-mobile": "10.20.1.14"}

for waf, proxy in (("waf-web", "reverse-proxy-web"), ("waf-mobile", "reverse-proxy-mobile")):
    print(f"\n-- {waf} -> {proxy}")
    s = svc[waf]
    env = {k: str(v) for k, v in s["environment"].items()}
    vols = {v["target"]: v for v in s.get("volumes", [])}
    unknown = set(env) - WAF_IMAGE_VARS
    check("todas las variables existen en la imagen del WAF (sin errores tipográficos)", not unknown, str(unknown))
    check("ModSecurity activo (MODSEC_RULE_ENGINE=On) y sin bajar paranoia ni umbrales",
          env.get("MODSEC_RULE_ENGINE", "").lower() == "on"
          and not {"BLOCKING_PARANOIA", "ANOMALY_INBOUND", "ANOMALY_OUTBOUND"} & set(env), env.get("MODSEC_RULE_ENGINE"))
    check("imagen CRS, audit log RelevantOnly a stdout, PORT 8080, contenedor y restart",
          s.get("image") == "owasp/modsecurity-crs:nginx" and s.get("container_name") == waf
          and s.get("restart") == "unless-stopped" and env.get("PORT") == "8080"
          and env.get("MODSEC_AUDIT_ENGINE") == "RelevantOnly" and env.get("MODSEC_AUDIT_LOG") == "/dev/stdout")
    check("cliente -> WAF: TLS 1.2/1.3 en :8443", env.get("SSL_PORT") == "8443" and env.get("SSL_PROTOCOLS") == "TLSv1.2 TLSv1.3")
    check("cliente -> WAF: cifrados ECDHE + AEAD", all(AEAD.match(c) for c in env.get("SSL_CIPHERS", "x").split(":")))
    edge = vols.get("/etc/nginx/edge-certs", {})
    check("certificado público (EDGE_TLS_DIR) montado en solo lectura, sin crear la ruta",
          env.get("SSL_CERT_FILE") == "/etc/nginx/edge-certs/tls.crt" and env.get("SSL_CERT_KEY_FILE") == "/etc/nginx/edge-certs/tls.key"
          and edge.get("source") == "${EDGE_TLS_DIR:?}" and edge.get("read_only") is True
          and edge.get("bind", {}).get("create_host_path") is False)
    check("HTTP del WAF nunca se reenvía: NGINX_ALWAYS_TLS_REDIRECT=on",
          env.get("NGINX_ALWAYS_TLS_REDIRECT") == "on"
          and env.get("SSL_REDIRECT_PORT") == ("${FRONTEND_HTTPS_PORT:?}" if waf == "waf-web" else "${MOBILE_HTTPS_PORT:?}"))
    check(f"WAF -> proxy por HTTPS: BACKEND=https://{proxy}:8443", env.get("BACKEND") == f"https://{proxy}:8443", env.get("BACKEND"))
    check("WAF -> proxy: verifica certificado (PROXY_SSL=on, PROXY_SSL_VERIFY=on) y envía SNI",
          env.get("PROXY_SSL") == "on" and env.get("PROXY_SSL_VERIFY") == "on" and env.get("PROXY_SSL_SERVER_NAME") == "on")
    check("WAF -> proxy: TLS 1.2/1.3 y cifrados ECDHE + AEAD",
          env.get("PROXY_SSL_PROTOCOLS") == "TLSv1.2 TLSv1.3" and all(AEAD.match(c) for c in env.get("PROXY_SSL_CIPHERS", "x").split(":")))
    ca = vols.get("/etc/nginx/upstream-ca/ca.crt", {})
    check("WAF confía SOLO en la CA interna (no en el almacén del sistema), montada en solo lectura",
          env.get("PROXY_SSL_CA_CERT_FILE") == "/etc/nginx/upstream-ca/ca.crt" and ca.get("source") == "${INTERNAL_CA_CERT:?}"
          and ca.get("read_only") is True)
    check("sin mTLS: no se cambian PROXY_SSL_CERT_FILE/KEY (la imagen usa el modo 'no-cert')",
          "PROXY_SSL_CERT_FILE" not in env and "PROXY_SSL_CERT_KEY_FILE" not in env)
    check("ninguna clave de CA montada en el WAF", not any("ca.key" in str(v.get("source", "")) for v in vols.values()))
    check(f"espera a que {proxy} esté healthy", as_mapping(s.get("depends_on")).get(proxy, {}).get("condition") == "service_healthy")
    check(f"WAF solo en public_network ({WAF_IPS[waf]}): no alcanza frontend, gateways ni servicios",
          {k: (v or {}).get("ipv4_address") for k, v in s["networks"].items()} == {"public_network": WAF_IPS[waf]},
          str(s["networks"]))
    approved = {"waf-web": "GET HEAD POST OPTIONS PATCH DELETE", "waf-mobile": "GET HEAD POST OPTIONS DELETE"}[waf]
    check(f"ALLOWED_METHODS aprobados ({approved}); PUT, TRACE, CONNECT siguen bloqueados por la 911100",
          set(env.get("ALLOWED_METHODS", "").split()) == set(approved.split()), env.get("ALLOWED_METHODS"))

    p = svc[proxy]
    pv = {v["target"] if isinstance(v, dict) else v.split(":")[1]: v for v in p.get("volumes", [])}
    var = "INTERNAL_WEB_TLS_DIR" if proxy.endswith("web") else "INTERNAL_MOBILE_TLS_DIR"
    cert = pv.get("/etc/nginx/certs", {})
    check(f"{proxy}: sin puertos publicados (solo se llega a través de {waf})", not p.get("ports"))
    check(f"{proxy}: certificado INTERNO (SAN = nombre del servicio) en solo lectura, sin crear la ruta",
          cert.get("source") == "${%s:?}" % var and cert.get("read_only") is True
          and cert.get("bind", {}).get("create_host_path") is False)
    rip = pv.get("/etc/nginx/conf.d/real-ip.conf")
    check(f"{proxy}: real-ip.conf montado en solo lectura",
          rip is not None and (rip.endswith(":ro") if isinstance(rip, str) else rip.get("read_only") is True))
    check(f"{proxy}: redes e IP conservadas (public_network, private_api)",
          {k: v["ipv4_address"] for k, v in p["networks"].items()} == PROXY_NETS[proxy], str(p["networks"]))

print("\n-- redes y cabecera de IP real")
nets = compose["networks"]
check("subredes 10.20.1/2/3.0/24; private_api y private_back internas; public_network no",
      [nets[n]["ipam"]["config"][0]["subnet"] for n in ("public_network", "private_api", "private_back")]
      == ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
      and nets["private_api"].get("internal") and nets["private_back"].get("internal")
      and not nets["public_network"].get("internal"))
check("sin redes de borde aparte (waf-edge eliminada)", set(nets) == {"public_network", "private_api", "private_back"}, str(set(nets)))
members = sorted(n for n, s in svc.items() if "public_network" in (s.get("networks") or {}))
check("public_network solo une los 2 WAF con los 2 proxies",
      members == ["reverse-proxy-mobile", "reverse-proxy-web", "waf-mobile", "waf-web"], str(members))
real_ip = (WAF_DIR / "real-ip.conf").read_text(encoding="utf-8-sig")
trusted = re.findall(r"set_real_ip_from\s+([\d./]+);", real_ip)
check(f"los proxies solo aceptan la IP real de los WAF ({', '.join(sorted(WAF_IPS.values()))}) por X-Real-IP",
      sorted(trusted) == sorted(WAF_IPS.values()) and re.search(r"real_ip_header\s+X-Real-IP;", real_ip), str(trusted))
check("el WAF reescribe X-Real-IP con su $remote_addr (REAL_IP_PROXY_HEADER y SET_REAL_IP_FROM por defecto)",
      not any({"REAL_IP_PROXY_HEADER", "SET_REAL_IP_FROM", "REAL_IP_HEADER"} & set(svc[w]["environment"]) for w in WAF_IPS))
for n in ("frontend", "api-gateway-component", "api-gateway-mobile"):
    check(f"{n}: sin puertos publicados y fuera de public_network",
          not svc[n].get("ports") and "public_network" not in (svc[n].get("networks") or {}))
gw = svc["api-gateway-component"]["environment"]
check("gateway web: COOKIE_SECURE y WS_ALLOWED_ORIGINS desde .env",
      gw["COOKIE_SECURE"] == "${COOKIE_SECURE:?}" and gw["WS_ALLOWED_ORIGINS"] == "${WS_ALLOWED_ORIGINS:?}")

print("\n-- secretos")
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
secrets = [f for f in tracked if re.search(r"(\.(key|pem|p12|pfx|crt)$)|(^|/)certs/", f)]
check("ningún certificado, clave o carpeta certs/ versionado en Git", not secrets, str(secrets[:5]))

print(f"\n{sum(results)}/{len(results)} comprobaciones estáticas superadas")
sys.exit(0 if all(results) else 1)