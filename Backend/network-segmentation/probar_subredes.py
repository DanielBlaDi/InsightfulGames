"""Pruebas de subredes del patrón Network Segmentation, contra el stack en ejecución.

    docker compose up --build -d
    python Backend/network-segmentation/probar_subredes.py          # escribe resultados-subredes.json

P1 - Matriz de alcanzabilidad entre subredes.
    Para cada subred (public_network 10.20.1.0/24, private_api 10.20.2.0/24, private_back 10.20.3.0/24)
    se arranca un contenedor sonda conectado SOLO a esa subred (equivale a un contenedor comprometido en
    ella) y se intenta abrir una conexión TCP a 15 destinos repartidos en las tres subredes (IP:puerto).
    Esperado: solo se alcanzan los destinos de la propia subred; todo cruce entre subredes falla.

P2 - Fronteras de subred: direccionamiento, rutas, DNS y salida.
    a) Auditoría con `docker network inspect`: subred, gateway e `internal` de cada red; cada IP dentro de
       su subred; miembros exactos de cada red; solo los proxies y los gateways tienen dos subredes; ningún
       contenedor está a la vez en public_network y private_back.
    b) Desde las sondas: tabla de rutas (/proc/net/route), resolución de nombres del DNS de Docker y salida
       a Internet (TCP 1.1.1.1:443 y DNS de example.com).
       Esperado: las subredes internas no tienen ruta por defecto ni salida; cada sonda solo resuelve los
       nombres de su subred y la IP resuelta pertenece a su subred.

Las sondas usan la imagen local python:3.12-slim (no descargan nada) y se borran al terminar (--rm).
No modifica ningún contenedor del sistema.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import subprocess
import sys
from pathlib import Path

PROJECT = "insightfulgames"
IMAGE = "python:3.12-slim"
TIMEOUT_S = 2.0

NETS = {
    "public_network": {"subnet": "10.20.1.0/24", "gateway": "10.20.1.1", "internal": False},
    "private_api": {"subnet": "10.20.2.0/24", "gateway": "10.20.2.1", "internal": True},
    "private_back": {"subnet": "10.20.3.0/24", "gateway": "10.20.3.1", "internal": True},
}

# Miembros de cada red según compose.yaml (nombres de contenedor).
EXPECTED = {
    "public_network": {"waf-web", "waf-mobile", "reverse-proxy-web", "reverse-proxy-mobile"},
    "private_api": {"reverse-proxy-web", "reverse-proxy-mobile", "frontend-component",
                    "api-gateway-component", "api-gateway-mobile"},
    "private_back": {"api-gateway-component", "api-gateway-mobile", "auth-component", "game-logic-component",
                     "single-player-component", "multiplayer-component", "tutor-component", "botcito-component",
                     "botcito-analysis-component", "profile-stats-component", "timeout-worker", "analysis-worker",
                     "rabbitmq-broker", "mongo-db", "mongo-analysis-db", "mysql-db", "postgres-profile-db"},
}
BRIDGES = {
    "reverse-proxy-web": {"public_network", "private_api"},
    "reverse-proxy-mobile": {"public_network", "private_api"},
    "api-gateway-component": {"private_api", "private_back"},
    "api-gateway-mobile": {"private_api", "private_back"},
}

# Destinos TCP de P1: (nombre, ip, puerto, subred del destino)
TARGETS = [
    ("waf-web", "10.20.1.13", 8443, "public_network"),
    ("waf-mobile", "10.20.1.14", 8443, "public_network"),
    ("reverse-proxy-web", "10.20.1.11", 8443, "public_network"),
    ("reverse-proxy-mobile", "10.20.1.12", 8443, "public_network"),
    ("reverse-proxy-web", "10.20.2.10", 8443, "private_api"),
    ("frontend-component", "10.20.2.12", 80, "private_api"),
    ("api-gateway-mobile", "10.20.2.13", 8090, "private_api"),
    ("api-gateway-component", "10.20.2.14", 8080, "private_api"),
    ("api-gateway-component", "10.20.3.11", 8080, "private_back"),
    ("auth-component", "10.20.3.12", 8081, "private_back"),
    ("game-logic-component", "10.20.3.13", 8082, "private_back"),
    ("rabbitmq-broker", "10.20.3.22", 5672, "private_back"),
    ("mongo-db", "10.20.3.23", 27017, "private_back"),
    ("mysql-db", "10.20.3.25", 3306, "private_back"),
    ("postgres-profile-db", "10.20.3.26", 5432, "private_back"),
]

# Nombres para la prueba de DNS de P2 y la subred en la que vive cada uno (None = externo).
DNS_NAMES = {
    "waf-web": {"public_network"},
    "reverse-proxy-web": {"public_network", "private_api"},
    "frontend-component": {"private_api"},
    "api-gateway-component": {"private_api", "private_back"},
    "auth-component": {"private_back"},
    "mongo-db": {"private_back"},
    "mysql-db": {"private_back"},
}
EXTERNAL_NAME = "example.com"
EGRESS = ("1.1.1.1", 443)

# Programa que corre dentro de cada sonda (lee la especificación de la variable SPEC).
PROBE = r'''
import json, os, socket, struct, time
spec = json.loads(os.environ["SPEC"])
def tcp(ip, port, t):
    s = socket.socket(); s.settimeout(t); t0 = time.monotonic()
    try:
        s.connect((ip, port)); r = "open"
    except ConnectionRefusedError:
        r = "refused"
    except socket.timeout:
        r = "timeout"
    except OSError as e:
        r = "unreachable (" + (e.strerror or str(e.errno)) + ")"
    finally:
        s.close()
    return r, round((time.monotonic() - t0) * 1000, 1)
def ip4(h):
    return socket.inet_ntoa(struct.pack("<I", int(h, 16)))
out = {"tcp": [], "dns": [], "routes": []}
for t in spec["tcp"]:
    r, ms = tcp(t["ip"], t["port"], spec["timeout"])
    out["tcp"].append(dict(t, resultado=r, ms=ms))
for name in spec["dns"]:
    try:
        ip = socket.gethostbyname(name)
    except OSError:
        ip = None
    out["dns"].append({"nombre": name, "ip": ip})
with open("/proc/net/route") as f:
    for line in f.read().splitlines()[1:]:
        p = line.split()
        out["routes"].append({"iface": p[0], "destino": ip4(p[1]), "gateway": ip4(p[2]), "mascara": ip4(p[7])})
r, ms = tcp(spec["egress"][0], spec["egress"][1], spec["timeout"])
out["egress_tcp"] = {"destino": "%s:%d" % tuple(spec["egress"]), "resultado": r, "ms": ms}
print(json.dumps(out))
'''


def docker(*args: str, stdin: str | None = None, check: bool = True) -> str:
    r = subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        sys.exit(f"docker {' '.join(args[:3])}...: {r.stderr.strip()}")
    return r.stdout


def net_name(short: str) -> str:
    return f"{PROJECT}_{short}"


def check(lista: list, prueba: str, ok: bool, detalle="") -> None:
    lista.append({"prueba": prueba, "ok": bool(ok), "detalle": detalle})
    print(f"  [{'OK ' if ok else 'FALLA'}] {prueba}" + (f"  -> {detalle}" if detalle not in ("", None) else ""))


def audit() -> tuple[list, dict]:
    """P2a: auditoría estática del direccionamiento con docker network inspect."""
    res: list = []
    membership: dict[str, dict[str, str]] = {}
    for short, cfg in NETS.items():
        info = json.loads(docker("network", "inspect", net_name(short)))[0]
        ipam = info["IPAM"]["Config"][0]
        check(res, f"{short}: subred {cfg['subnet']}, gateway {cfg['gateway']}, internal={cfg['internal']}",
              ipam.get("Subnet") == cfg["subnet"] and ipam.get("Gateway") == cfg["gateway"]
              and info["Internal"] == cfg["internal"],
              f"{ipam.get('Subnet')} gw={ipam.get('Gateway')} internal={info['Internal']}")
        members = {c["Name"]: c["IPv4Address"].split("/")[0] for c in info["Containers"].values()}
        membership[short] = members
        net = ipaddress.ip_network(cfg["subnet"])
        fuera = {n: ip for n, ip in members.items() if ipaddress.ip_address(ip) not in net}
        check(res, f"{short}: las {len(members)} IP están dentro de {cfg['subnet']}", not fuera, fuera or "")
        sobran, faltan = set(members) - EXPECTED[short], EXPECTED[short] - set(members)
        check(res, f"{short}: miembros exactos según el diseño ({len(EXPECTED[short])})",
              not sobran and not faltan, {"sobran": sorted(sobran), "faltan": sorted(faltan)} if sobran or faltan else "")
    por_contenedor: dict[str, set] = {}
    for short, members in membership.items():
        for n in members:
            por_contenedor.setdefault(n, set()).add(short)
    multi = {n: sorted(s) for n, s in por_contenedor.items() if len(s) > 1}
    check(res, "solo los 2 proxies y los 2 gateways están en dos subredes",
          {n: set(s) for n, s in multi.items()} == BRIDGES, multi)
    salto = sorted(n for n, s in por_contenedor.items() if {"public_network", "private_back"} <= s)
    check(res, "ningún contenedor une public_network con private_back (no se salta private_api)", not salto, salto or "")
    # Redes del proyecto que no están en el diseño (informativo si no tienen contenedores).
    otras = []
    for n in docker("network", "ls", "--filter", f"name={PROJECT}_", "--format", "{{.Name}}").split():
        if n not in {net_name(s) for s in NETS}:
            info = json.loads(docker("network", "inspect", n))[0]
            otras.append({"red": n, "subred": (info["IPAM"]["Config"] or [{}])[0].get("Subnet"),
                          "contenedores": len(info["Containers"])})
    check(res, "ningún contenedor está en redes ajenas al diseño",
          all(o["contenedores"] == 0 for o in otras), otras or "")
    return res, membership


def run_probe(short: str) -> dict:
    spec = {"timeout": TIMEOUT_S,
            "tcp": [{"nombre": n, "ip": ip, "puerto": p, "subred": s} for n, ip, p, s in TARGETS],
            "dns": list(DNS_NAMES) + [EXTERNAL_NAME], "egress": list(EGRESS)}
    spec["tcp"] = [dict(t, port=t["puerto"]) for t in spec["tcp"]]
    out = docker("run", "--rm", "-i", "--name", f"subnet-probe-{short.replace('_', '-')}",
                 "--network", net_name(short), "--label", "insightfulgames.probe=subnet",
                 "-e", "SPEC=" + json.dumps(spec), IMAGE, "python", "-", stdin=PROBE)
    data = json.loads(out.strip().splitlines()[-1])
    for t in data["tcp"]:
        t.pop("port", None)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=Path(__file__).with_name("resultados-subredes.json"))
    args = ap.parse_args()

    if not docker("images", "-q", IMAGE).strip():
        sys.exit(f"Falta la imagen local {IMAGE} (docker pull {IMAGE}).")

    print("P2a - auditoría de direccionamiento (docker network inspect)")
    auditoria, membership = audit()

    p1_matriz, p2_sondas = [], []
    print("\nP1 - matriz de alcanzabilidad entre subredes (una sonda por subred)")
    for short in NETS:
        data = run_probe(short)
        print(f" sonda en {short}:")
        for t in data["tcp"]:
            alcanzado = t["resultado"] in ("open", "refused")
            esperado = t["subred"] == short
            t.update(sonda=short, alcanzado=alcanzado, esperado=esperado, ok=alcanzado == esperado)
            p1_matriz.append(t)
            print(f"  [{'OK ' if t['ok'] else 'FALLA'}] -> {t['nombre']:<22} {t['ip']}:{t['puerto']:<5} "
                  f"{t['resultado']:<28} {t['ms']:>7.1f} ms  (esperado {'alcanzable' if esperado else 'bloqueado'})")

        print(f" P2b - fronteras vistas desde la sonda en {short}:")
        sub = ipaddress.ip_network(NETS[short]["subnet"])
        checks: list = []
        default = [r for r in data["routes"] if r["destino"] == "0.0.0.0"]
        if NETS[short]["internal"]:
            check(checks, f"{short}: sin ruta por defecto (solo la ruta de su /24)",
                  not default and all(r["destino"] == str(sub.network_address) for r in data["routes"]),
                  data["routes"])
        else:
            check(checks, f"{short}: ruta por defecto vía {NETS[short]['gateway']} (red de borde, no interna)",
                  any(r["gateway"] == NETS[short]["gateway"] for r in default), data["routes"])
        for d in data["dns"]:
            if d["nombre"] == EXTERNAL_NAME:
                continue
            debe = short in DNS_NAMES[d["nombre"]]
            ok = (d["ip"] is not None) == debe and (d["ip"] is None or ipaddress.ip_address(d["ip"]) in sub)
            check(checks, f"{short}: '{d['nombre']}' {'se resuelve a una IP de la subred' if debe else 'no se resuelve'}",
                  ok, d["ip"] or "sin respuesta")
        ext = next(d for d in data["dns"] if d["nombre"] == EXTERNAL_NAME)
        eg = data["egress_tcp"]
        sale = eg["resultado"] in ("open", "refused")
        if NETS[short]["internal"]:
            check(checks, f"{short}: sin salida a Internet (TCP {eg['destino']})", not sale, eg["resultado"])
            check(checks, f"{short}: no resuelve nombres externos ({EXTERNAL_NAME})", ext["ip"] is None,
                  ext["ip"] or "sin respuesta")
        else:
            checks.append({"prueba": f"{short}: salida a Internet (informativo; red de borde no interna)",
                           "ok": True, "informativo": True,
                           "detalle": f"TCP {eg['destino']}: {eg['resultado']}; DNS {EXTERNAL_NAME}: {ext['ip']}"})
            print(f"  [INFO] {checks[-1]['prueba']} -> {checks[-1]['detalle']}")
        p2_sondas.append({"sonda": short, "checks": checks, "rutas": data["routes"], "dns": data["dns"],
                          "egress_tcp": eg})

    permitidos = [t for t in p1_matriz if t["esperado"]]
    prohibidos = [t for t in p1_matriz if not t["esperado"]]
    p2_checks = auditoria + [c for s in p2_sondas for c in s["checks"] if not c.get("informativo")]
    resumen = {
        "P1": {"intentos": len(p1_matriz),
               "permitidos_alcanzados": sum(t["alcanzado"] for t in permitidos), "permitidos": len(permitidos),
               "prohibidos_bloqueados": sum(not t["alcanzado"] for t in prohibidos), "prohibidos": len(prohibidos),
               "violaciones": sum(not t["ok"] for t in p1_matriz)},
        "P2": {"superadas": sum(c["ok"] for c in p2_checks), "total": len(p2_checks)},
    }
    out = {"fecha": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "imagen_sonda": IMAGE,
           "timeout_tcp_s": TIMEOUT_S, "redes": NETS, "resumen": resumen,
           "P1_matriz": p1_matriz, "P2_auditoria": auditoria, "P2_sondas": p2_sondas,
           "miembros": {k: dict(sorted(v.items())) for k, v in membership.items()}}
    args.salida.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nP1: {resumen['P1']['permitidos_alcanzados']}/{resumen['P1']['permitidos']} flujos permitidos alcanzados, "
          f"{resumen['P1']['prohibidos_bloqueados']}/{resumen['P1']['prohibidos']} cruces bloqueados, "
          f"{resumen['P1']['violaciones']} violaciones")
    print(f"P2: {resumen['P2']['superadas']}/{resumen['P2']['total']} comprobaciones superadas")
    print(f"Resultados: {args.salida}")
    sys.exit(0 if resumen["P1"]["violaciones"] == 0 and resumen["P2"]["superadas"] == resumen["P2"]["total"] else 1)


if __name__ == "__main__":
    main()
