"""Genera el informe HTML de las pruebas de rendimiento a partir de performance/resultados.

    python performance/informe.py          -> performance/resultados/informe.html

Solo usa la biblioteca estándar. El PDF se imprime con Edge o Chrome sin cabeceras:
    msedge --headless --no-pdf-header-footer --print-to-pdf=docs/pruebas-rendimiento-k6.pdf performance/resultados/informe.html

Los números, tablas y gráficos salen de los archivos de resultados. El texto de análisis (ANALISIS, abajo) se
escribió para la corrida documentada y hay que revisarlo si se vuelven a ejecutar las pruebas.
"""

import csv
import gzip
import html
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

from informe_texto import TEXTO

R = Path(__file__).resolve().parent / "resultados"
SALIDA = R / "informe.html"

# Paleta de referencia validada (modo claro): categóricos en orden fijo y un color de estado crítico
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
CRIT = "#d03b3b"
INK, INK2, MUTED, GRID, SURF, BANDA = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb", "#f1f0ec"
FONT = "font-family:'Segoe UI',Arial,sans-serif"
CPU_HOST = 12  # CPU que Docker Desktop asigna a su máquina virtual (docker info: NCPU)


# =============================================================================================== datos


def pct(valores, p):
    if not valores:
        return None
    s = sorted(valores)
    k = (len(s) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    return s[f] + (s[c] - s[f]) * (k - f)


def etiquetas(extra):
    """extra_tags de k6 ('a=1&b=2') -> dict."""
    return {k: v[0] for k, v in parse_qs(extra or "").items()}


def leer_k6(prueba, metricas):
    """{métrica: [(t_s, valor, name, status, extra_dict)]} del CSV de k6."""
    out = defaultdict(list)
    ruta = R / f"{prueba}.csv.gz"
    if not ruta.exists():
        return out
    try:
        with gzip.open(ruta, "rt", encoding="utf-8", newline="") as f:
            for x in csv.DictReader(f):
                m = x["metric_name"]
                if m in metricas:
                    out[m].append((int(x["timestamp"]), float(x["metric_value"]), x["name"], x["status"],
                                   etiquetas(x["extra_tags"])))
    except EOFError:
        pass  # el CSV todavía se está escribiendo: se usa lo leído
    return out


def resumen(prueba):
    ruta = R / f"{prueba}-resumen.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def ventanas():
    ruta = R / "ventanas.json"
    if not ruta.exists():
        return {}
    v = json.loads(ruta.read_text(encoding="utf-8-sig"))
    v = v if isinstance(v, list) else [v]
    return {x["prueba"]: x for x in v}


def leer_recursos():
    filas = []
    ruta = R / "recursos.csv"
    if not ruta.exists():
        return filas
    with open(ruta, encoding="utf-8") as f:
        for x in csv.DictReader(f):
            filas.append((int(x["ts_ms"]) / 1000, x["origen"], x["nombre"],
                          float(x["cpu_pct"]) if x["cpu_pct"] not in ("", None) else None,
                          float(x["mem_mb"]) if x["mem_mb"] not in ("", None) else None))
    return filas


def linea_tiempo(datos, paso=10):
    """Series por ventanas de `paso` s: VUs, peticiones/s, p50/p95 y % de fallos. x en segundos desde el inicio."""
    tiempos = [t for m in ("vus", "http_req_duration") for t, *_ in datos.get(m, [])]
    if not tiempos:
        return None
    t0 = min(tiempos)
    vus, dur, fallos = defaultdict(list), defaultdict(list), defaultdict(list)
    for t, v, *_ in datos.get("vus", []):
        vus[(t - t0) // paso].append(v)
    for t, v, *_ in datos.get("http_req_duration", []):
        dur[(t - t0) // paso].append(v)
    for t, v, *_ in datos.get("http_req_failed", []):
        fallos[(t - t0) // paso].append(v)
    n = max(list(vus) + list(dur) + [0]) + 1
    serie = []
    for b in range(n):
        d = dur.get(b, [])
        serie.append({
            "x": b * paso + paso / 2,
            "vus": max(vus[b]) if vus.get(b) else 0,
            "rps": len(d) / paso,
            "p50": pct(d, 50), "p95": pct(d, 95),
            "fallos": (100 * sum(fallos[b]) / len(fallos[b])) if fallos.get(b) else 0,
        })
    return {"t0": t0, "paso": paso, "serie": serie, "duracion": n * paso}


def por_endpoint(datos):
    lat, fal = defaultdict(list), defaultdict(list)
    for _, v, name, *_ in datos.get("http_req_duration", []):
        lat[name].append(v)
    for _, v, name, *_ in datos.get("http_req_failed", []):
        fal[name].append(v)
    filas = []
    for name, v in lat.items():
        f = fal.get(name, [])
        filas.append({"name": name, "n": len(v), "p50": pct(v, 50), "p95": pct(v, 95), "p99": pct(v, 99),
                      "max": max(v), "fallos": 100 * sum(f) / len(f) if f else 0})
    return sorted(filas, key=lambda x: -x["p95"])


def tramo(datos, t0, desde, hasta):
    """Métricas HTTP entre los segundos [desde, hasta) del inicio de la prueba."""
    d = [v for t, v, *_ in datos.get("http_req_duration", []) if desde <= t - t0 < hasta]
    f = [v for t, v, *_ in datos.get("http_req_failed", []) if desde <= t - t0 < hasta]
    tipos = defaultdict(list)
    for t, v, _, _, ex in datos.get("http_req_duration", []):
        if desde <= t - t0 < hasta:
            tipos[ex.get("tipo", "?")].append(v)
    return {"rps": len(d) / max(1, hasta - desde), "p50": pct(d, 50), "p95": pct(d, 95), "p99": pct(d, 99),
            "fallos": 100 * sum(f) / len(f) if f else 0, "n": len(d),
            "tipos": {k: pct(v, 95) for k, v in tipos.items()}}


def recursos_en(recursos, desde_s, hasta_s):
    """CPU media y p90 por contenedor, CPU del host y de k6, paginación y sonda en una ventana de tiempo absoluto."""
    cpu, mem = defaultdict(list), defaultdict(list)
    host, k6, pag, sonda = [], [], [], []
    imposibles = 0
    for t, origen, nombre, c, m in recursos:
        if not desde_s <= t <= hasta_s:
            continue
        if origen == "contenedor":
            if c is not None and c > CPU_HOST * 100:
                imposibles += 1  # lectura imposible: la máquina virtual se detuvo entre dos muestras
            elif c is not None:
                cpu[nombre].append(c)
            if m is not None:
                mem[nombre].append(m)
        elif nombre == "cpu_total" and c is not None:
            host.append(c)
        elif nombre == "k6" and c is not None:
            k6.append(c)
        elif nombre == "paginacion" and m is not None:
            pag.append(m)
        elif nombre == "health_ms" and c is not None:
            sonda.append(c)
    contenedores = {n: {"media": sum(v) / len(v), "p90": pct(v, 90), "mem": max(mem.get(n, [0]))}
                    for n, v in cpu.items() if v}
    total = defaultdict(float)
    return {"contenedores": contenedores, "host": host, "k6": k6, "paginacion": pag, "sonda": sonda,
            "imposibles": imposibles,
            "vm_media": sum(c["media"] for c in contenedores.values()) / CPU_HOST}


def serie_recursos(recursos, desde_s, hasta_s, nombres):
    """Series de CPU (puntos (x, y)) por contenedor, del host y de la sonda, con x en s desde `desde_s`."""
    s = defaultdict(list)
    for t, origen, nombre, c, m in recursos:
        if not desde_s <= t <= hasta_s or c is None:
            continue
        x = t - desde_s
        if origen == "contenedor" and nombre in nombres and c <= CPU_HOST * 100:
            s[nombre].append((x, c))
        elif nombre == "cpu_total":
            s["host"].append((x, c))
        elif nombre == "health_ms":
            s["sonda"].append((x, c if c >= 0 else 20000))
    return s


# ============================================================================================ gráficos


def esc(t):
    return html.escape(str(t))


def ticks(maximo, n=5):
    if maximo <= 0:
        return 1, [0, 1]
    bruto = maximo / n
    mag = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= bruto:
            paso = m * mag
            break
    tope = paso * math.ceil(maximo / paso)
    return tope, [i * paso for i in range(int(round(tope / paso)) + 1)]


def fmt(v, dec=0):
    if v is None:
        return "—"
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def grafico_lineas(titulo, series, x_max, y_max=None, unidad="", alto=150, bandas=None, ancho=680,
                   eje_x="minutos desde el inicio", y_log=False, umbral=None):
    """series: [(nombre, color, [(x_s, y)], discontinua)]. bandas: [(x0, x1, texto)]. umbral: (y, texto)."""
    ml, mr, mt, mb = 52, 128, 26, 28
    pw, ph = ancho - ml - mr, alto - mt - mb
    valores = [y for _, _, pts, _ in series for _, y in pts if y is not None]
    if umbral:
        valores.append(umbral[0])
    tope, marcas = ticks(y_max if y_max else (max(valores) if valores else 1))
    xs = lambda x: ml + pw * x / x_max
    ys = lambda y: mt + ph * (1 - min(y, tope) / tope)
    o = [f'<svg viewBox="0 0 {ancho} {alto}" width="100%" style="{FONT};background:{SURF}" role="img" aria-label="{esc(titulo)}">',
         f'<text x="{ml}" y="15" font-size="11.5" font-weight="600" fill="{INK}">{esc(titulo)}</text>']
    for i, (x0, x1, txt) in enumerate(bandas or []):
        if i % 2 == 0:
            o.append(f'<rect x="{xs(x0):.1f}" y="{mt}" width="{xs(x1) - xs(x0):.1f}" height="{ph}" fill="{BANDA}"/>')
        o.append(f'<text x="{(xs(x0) + xs(x1)) / 2:.1f}" y="{mt + 9}" font-size="8" fill="{INK2}" text-anchor="middle">{esc(txt)}</text>')
    for m in marcas:
        o.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{ys(m):.1f}" y2="{ys(m):.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{ml - 5}" y="{ys(m) + 3:.1f}" font-size="8.5" fill="{INK2}" text-anchor="end">{fmt(m, 0 if m >= 10 or m == 0 else 1)}</text>')
    corto = x_max <= 120  # pruebas cortas: eje en segundos
    if corto and eje_x == "minutos desde el inicio":
        eje_x = "segundos desde el inicio"
    paso_x = 10 if corto else (60 if x_max <= 900 else 120)
    x = 0
    while x <= x_max + 0.1:
        etiqueta = fmt(x, 0) if corto else fmt(x / 60, 0 if x % 60 == 0 else 1)
        o.append(f'<text x="{xs(x):.1f}" y="{mt + ph + 12}" font-size="8.5" fill="{INK2}" text-anchor="middle">{etiqueta}</text>')
        x += paso_x
    o.append(f'<text x="{ml + pw / 2}" y="{alto - 3}" font-size="8.5" fill="{INK2}" text-anchor="middle">{esc(eje_x)}</text>')
    o.append(f'<text x="11" y="{mt + ph / 2}" font-size="8.5" fill="{INK2}" text-anchor="middle" transform="rotate(-90 11 {mt + ph / 2})">{esc(unidad)}</text>')
    if umbral:
        o.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{ys(umbral[0]):.1f}" y2="{ys(umbral[0]):.1f}" stroke="{CRIT}" stroke-dasharray="4 3"/>')
        o.append(f'<text x="{ml + pw - 2}" y="{ys(umbral[0]) - 3:.1f}" font-size="8" fill="{CRIT}" text-anchor="end">{esc(umbral[1])}</text>')
    etiquetas_fin = []
    for nombre, color, pts, discontinua in series:
        pts = [(px, py) for px, py in pts if py is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{xs(px):.1f},{ys(py):.1f}" for i, (px, py) in enumerate(pts))
        guion = ' stroke-dasharray="5 3"' if discontinua else ""
        o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"{guion}/>')
        etiquetas_fin.append([ys(pts[-1][1]), nombre, color])
    etiquetas_fin.sort()
    for i in range(1, len(etiquetas_fin)):
        if etiquetas_fin[i][0] - etiquetas_fin[i - 1][0] < 11:
            etiquetas_fin[i][0] = etiquetas_fin[i - 1][0] + 11
    for y, nombre, color in etiquetas_fin:
        o.append(f'<rect x="{ml + pw + 8}" y="{y - 2:.1f}" width="10" height="3" rx="1.5" fill="{color}"/>')
        o.append(f'<text x="{ml + pw + 22}" y="{y + 3:.1f}" font-size="8.5" fill="{INK}">{esc(nombre)}</text>')
    o.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}" stroke="{MUTED}"/>')
    o.append("</svg>")
    return "".join(o)


def grafico_barras_h(titulo, filas, unidad, ancho=680, alto_fila=19, fmt_valor=None, max_x=None):
    """filas: [(etiqueta, valor, color)]."""
    ml, mr, mt = 200, 70, 24
    alto = mt + alto_fila * len(filas) + 8
    vmax = max_x or max([v for _, v, _ in filas] + [1e-9])
    pw = ancho - ml - mr
    o = [f'<svg viewBox="0 0 {ancho} {alto}" width="100%" style="{FONT};background:{SURF}" role="img" aria-label="{esc(titulo)}">',
         f'<text x="0" y="14" font-size="11.5" font-weight="600" fill="{INK}">{esc(titulo)}</text>']
    for i, (etq, v, color) in enumerate(filas):
        y = mt + i * alto_fila
        bw = max(0.0, pw * v / vmax)
        o.append(f'<text x="{ml - 6}" y="{y + 12}" font-size="9" fill="{INK}" text-anchor="end">{esc(etq)}</text>')
        if bw > 0:
            o.append(f'<rect x="{ml}" y="{y + 3}" width="{bw:.1f}" height="12" rx="3" fill="{color}"/>')
        texto = fmt_valor(v) if fmt_valor else fmt(v, 1)
        o.append(f'<text x="{ml + bw + 5:.1f}" y="{y + 12.5}" font-size="9" font-weight="600" fill="{INK}">{esc(texto)} {esc(unidad)}</text>')
    o.append("</svg>")
    return "".join(o)


def grafico_barras(titulo, categorias, series, unidad, ancho=680, alto=190, y_max=None, umbral=None):
    """Barras verticales agrupadas. series: [(nombre, color, [valor por categoría])]."""
    ml, mr, mt, mb = 52, 20, 40, 30
    pw, ph = ancho - ml - mr, alto - mt - mb
    valores = [v for _, _, vs in series for v in vs if v is not None]
    tope, marcas = ticks(y_max or max(valores + [umbral[0] if umbral else 0, 1e-9]))
    ys = lambda y: mt + ph * (1 - min(y, tope) / tope)
    o = [f'<svg viewBox="0 0 {ancho} {alto}" width="100%" style="{FONT};background:{SURF}" role="img" aria-label="{esc(titulo)}">',
         f'<text x="0" y="14" font-size="11.5" font-weight="600" fill="{INK}">{esc(titulo)}</text>']
    lx = 0
    for nombre, color, _ in series:
        o.append(f'<rect x="{lx}" y="22" width="10" height="10" rx="2" fill="{color}"/><text x="{lx + 14}" y="31" font-size="9" fill="{INK}">{esc(nombre)}</text>')
        lx += 22 + 5.6 * len(nombre) + 10
    for m in marcas:
        o.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{ys(m):.1f}" y2="{ys(m):.1f}" stroke="{GRID}"/>')
        o.append(f'<text x="{ml - 5}" y="{ys(m) + 3:.1f}" font-size="8.5" fill="{INK2}" text-anchor="end">{fmt(m, 0 if m >= 10 or m == 0 else 1)}</text>')
    if umbral:
        o.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{ys(umbral[0]):.1f}" y2="{ys(umbral[0]):.1f}" stroke="{CRIT}" stroke-dasharray="4 3"/>')
        o.append(f'<text x="{ml + pw - 2}" y="{ys(umbral[0]) - 3:.1f}" font-size="8" fill="{CRIT}" text-anchor="end">{esc(umbral[1])}</text>')
    grupo = pw / max(1, len(categorias))
    bw = min(34, (grupo - 14) / max(1, len(series)))
    for i, cat in enumerate(categorias):
        x0 = ml + i * grupo + (grupo - bw * len(series) - 2 * (len(series) - 1)) / 2
        for j, (_, color, vs) in enumerate(series):
            v = vs[i]
            if v is None:
                continue
            x = x0 + j * (bw + 2)
            o.append(f'<rect x="{x:.1f}" y="{ys(v):.1f}" width="{bw:.1f}" height="{mt + ph - ys(v):.1f}" rx="2" fill="{color}"/>')
            o.append(f'<text x="{x + bw / 2:.1f}" y="{ys(v) - 3:.1f}" font-size="8" fill="{INK}" text-anchor="middle">{fmt(v, 0 if v >= 10 else 1)}</text>')
        o.append(f'<text x="{ml + i * grupo + grupo / 2:.1f}" y="{mt + ph + 13}" font-size="9" fill="{INK}" text-anchor="middle">{esc(cat)}</text>')
    o.append(f'<text x="11" y="{mt + ph / 2}" font-size="8.5" fill="{INK2}" text-anchor="middle" transform="rotate(-90 11 {mt + ph / 2})">{esc(unidad)}</text>')
    o.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{mt + ph}" y2="{mt + ph}" stroke="{MUTED}"/>')
    o.append("</svg>")
    return "".join(o)


def panel_tiempo(lt, bandas, umbral_p95=None, titulo=""):
    """Cuatro gráficos apilados con el mismo eje de tiempo (en vez de un gráfico con dos ejes)."""
    s, xmax = lt["serie"], lt["duracion"]
    pts = lambda k: [(p["x"], p[k]) for p in s]
    return "".join([
        f'<div class="chart">{grafico_lineas(f"{titulo} · usuarios virtuales activos", [("VUs", C[0], pts("vus"), False)], xmax, unidad="VUs", alto=120, bandas=bandas)}</div>',
        f'<div class="chart">{grafico_lineas("Peticiones por segundo", [("peticiones/s", C[2], pts("rps"), False)], xmax, unidad="pet./s", alto=120, bandas=bandas)}</div>',
        f'<div class="chart">{grafico_lineas("Latencia (ventanas de 10 s)", [("p95", C[1], pts("p95"), False), ("p50", C[0], pts("p50"), False)], xmax, unidad="ms", alto=150, bandas=bandas, umbral=umbral_p95)}</div>',
        f'<div class="chart">{grafico_lineas("Peticiones fallidas", [("% fallidas", CRIT, pts("fallos"), False)], xmax, unidad="%", alto=110, bandas=bandas, y_max=max(5, max(p["fallos"] for p in s) * 1.1))}</div>',
    ])


# ============================================================================================== tablas


def tabla(cabeceras, filas, clases=None):
    th = "".join(f"<th>{esc(h)}</th>" for h in cabeceras) if cabeceras else ""
    cuerpo = []
    for i, f in enumerate(filas):
        cls = f' class="{clases[i]}"' if clases and clases[i] else ""
        cuerpo.append(f"<tr{cls}>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>")
    cabecera = f"<tr>{th}</tr>" if th else ""
    return f"<table>{cabecera}{''.join(cuerpo)}</table>"


def umbrales(res):
    """[(expresión de la métrica, condición, ok, valor medido)] del resumen de k6."""
    out = []
    for nombre, m in (res or {}).get("metrics", {}).items():
        for cond, t in (m.get("thresholds") or {}).items():
            out.append((nombre, cond, t.get("ok"), m.get("values", {})))
    return out


def valor_umbral(cond, valores):
    clave = cond.split("<")[0].split(">")[0].strip()
    v = valores.get(clave)
    if v is None:
        return "—"
    if clave == "rate":
        return f"{fmt(100 * v, 2)} %"
    if clave == "count":
        return fmt(v)
    return f"{fmt(v)} ms"


def ok(b):
    return '<span class="ok">Cumple</span>' if b else '<span class="bad">No cumple</span>'


# ============================================================================================ secciones

# Tramos de cada perfil (segundos desde el inicio), iguales a las etapas de k6/flujos.js
BANDAS = {
    "carga": [(0, 60, "subida"), (60, 360, "40 VUs estables"), (360, 390, "bajada")],
    "estres": [(0, 60, "→50"), (60, 180, "50 VUs"), (180, 240, "→100"), (240, 360, "100 VUs"),
               (360, 420, "→200"), (420, 540, "200 VUs"), (540, 600, "→300"), (600, 720, "300 VUs"), (720, 750, "")],
    "pico": [(0, 30, "10 VUs"), (30, 40, "↑"), (40, 100, "200 VUs"), (100, 110, "↓"), (110, 170, "10 VUs"), (170, 180, "")],
}
MESETAS = {
    "carga": [("40 VUs", 70, 360)],
    "estres": [("50 VUs", 70, 180), ("100 VUs", 250, 360), ("200 VUs", 430, 540), ("300 VUs", 610, 720)],
    "pico": [("antes: 10 VUs", 5, 30), ("pico: 200 VUs", 45, 100), ("después: 10 VUs", 115, 170)],
}


def filas_tramos(datos, t0, tramos):
    filas = []
    for nombre, a, b in tramos:
        t = tramo(datos, t0, a, b)
        filas.append([esc(nombre), fmt(t["rps"], 1), f"{fmt(t['p50'])} ms", f"{fmt(t['p95'])} ms", f"{fmt(t['p99'])} ms",
                      f"{fmt(t['tipos'].get('pagina'))} ms", f"{fmt(t['tipos'].get('lectura'))} ms",
                      f"{fmt(t['tipos'].get('escritura'))} ms", f"{fmt(t['fallos'], 2)} %"])
    return tabla(["Tramo", "pet./s", "p50", "p95", "p99", "p95 páginas", "p95 lecturas", "p95 escrituras", "fallidas"], filas)


def tabla_endpoints(datos, n=None):
    filas = [[f"<code>{esc(e['name'])}</code>", fmt(e["n"]), f"{fmt(e['p50'])} ms", f"{fmt(e['p95'])} ms",
              f"{fmt(e['p99'])} ms", f"{fmt(e['max'])} ms", f"{fmt(e['fallos'], 2)} %"]
             for e in por_endpoint(datos)[:n]]
    return tabla(["Endpoint", "peticiones", "p50", "p95", "p99", "máx", "fallidas"], filas)


def tabla_umbrales(res):
    filas = [[f"<code>{esc(n)}</code>", f"<code>{esc(c)}</code>", valor_umbral(c, v), ok(b)] for n, c, b, v in umbrales(res)]
    return tabla(["Métrica", "Objetivo", "Medido", ""], filas)


def tabla_recursos(rec, n=10):
    filas = []
    for nombre, c in sorted(rec["contenedores"].items(), key=lambda kv: -kv[1]["media"])[:n]:
        filas.append([f"<code>{esc(nombre)}</code>", f"{fmt(c['media'], 0)} %", f"{fmt(c['p90'], 0)} %", f"{fmt(c['mem'], 0)} MB"])
    return tabla(["Contenedor", "CPU media", "CPU p90", "memoria máx."], filas)


def resumen_sonda(rec):
    s = [v for v in rec["sonda"] if v is not None]
    lentas = [v for v in s if v < 0 or v > 1000]
    return {"n": len(s), "lentas": len(lentas), "max": max(s) if s else None, "p50": pct([v for v in s if v >= 0], 50)}


def seccion_prueba(nombre, titulo, intro, recursos, vent, umbral_p95=None):
    datos = leer_k6(nombre, {"vus", "http_req_duration", "http_req_failed"})
    res = resumen(nombre)
    if not datos or res is None:
        return f"<h2>{esc(titulo)}</h2><p><i>Sin resultados.</i></p>", None
    lt = linea_tiempo(datos)
    partes = [f'<h2 class="pb">{esc(titulo)}</h2>', intro]
    m = res["metrics"]
    partes.append(tabla(["Peticiones", "pet./s (media)", "fallidas", "checks", "p50", "p95", "p99"], [[
        fmt(m["http_reqs"]["values"]["count"]), fmt(m["http_reqs"]["values"]["rate"], 1),
        f"{fmt(100 * m['http_req_failed']['values']['rate'], 2)} %", f"{fmt(100 * m['checks']['values']['rate'], 2)} %",
        f"{fmt(m['http_req_duration']['values']['med'])} ms", f"{fmt(m['http_req_duration']['values']['p(95)'])} ms",
        f"{fmt(m['http_req_duration']['values']['p(99)'])} ms"]]))
    if nombre in BANDAS:
        partes.append(panel_tiempo(lt, BANDAS[nombre], umbral_p95, titulo.split("·")[0].strip()))
    if nombre in MESETAS:
        partes.append("<h3>Por tramo de carga</h3>" + filas_tramos(datos, lt["t0"], MESETAS[nombre]))
    partes.append("<h3>Objetivos (umbrales de k6)</h3>" + tabla_umbrales(res))
    partes.append("<h3>Por endpoint</h3>" + tabla_endpoints(datos))
    v = vent.get(nombre)
    rec = recursos_en(recursos, v["inicio"] / 1000, v["fin"] / 1000) if v else None
    return "".join(partes), {"lt": lt, "datos": datos, "res": res, "rec": rec}


def seccion_bot(recursos, vent, intro):
    datos = leer_k6("bot", {"bot_respuesta", "ws_jugada_aplicada", "bot_jugada_ok", "bot_partida_ok", "bot_errores"})
    res = resumen("bot")
    if res is None:
        return "<h2>Bot por WebSocket</h2><p><i>Sin resultados.</i></p>", None
    por = defaultdict(lambda: defaultdict(list))
    motivos = defaultdict(lambda: defaultdict(int))
    for metrica, filas in datos.items():
        for _, v, _, _, ex in filas:
            n = int(ex.get("concurrencia", "0") or 0)
            if metrica == "bot_errores":
                motivos[n][ex.get("motivo", "?")] += int(v)
            else:
                por[n][metrica].append(v)
    niveles = sorted(n for n in por if n > 0)
    filas = []
    p50s, p95s, okj, okp = [], [], [], []
    for n in niveles:
        d = por[n]
        r = d["bot_respuesta"]
        jo = d["bot_jugada_ok"]
        po = d["bot_partida_ok"]
        p50s.append(pct(r, 50))
        p95s.append(pct(r, 95))
        okj.append(100 * sum(jo) / len(jo) if jo else None)
        okp.append(100 * sum(po) / len(po) if po else None)
        mot = ", ".join(f"{k}: {v}" for k, v in sorted(motivos[n].items(), key=lambda kv: -kv[1])) or "—"
        filas.append([str(n), fmt(len(r)), f"{fmt(pct(r, 50))} ms", f"{fmt(pct(r, 95))} ms",
                      f"{fmt(pct(d['ws_jugada_aplicada'], 95))} ms", f"{fmt(okj[-1], 1)} %", f"{fmt(okp[-1], 1)} %", esc(mot)])
    cats = [f"{n} partida" + ("s" if n > 1 else "") for n in niveles]
    partes = ['<h2 class="pb">Partidas contra el bot por WebSocket</h2>', intro,
              '<div class="chart">' + grafico_barras("Respuesta del bot según partidas simultáneas", cats,
                                                     [("p50", C[0], p50s), ("p95", C[1], p95s)], "ms",
                                                     umbral=(3000, "objetivo p95 < 3 s")) + "</div>",
              '<div class="chart">' + grafico_barras("Jugadas del bot que llegan y partidas completas", cats,
                                                     [("jugadas del bot OK", C[2], okj), ("partidas completas", C[0], okp)], "%",
                                                     y_max=100) + "</div>",
              tabla(["Partidas simultáneas", "jugadas del bot", "respuesta p50", "respuesta p95", "jugada humana p95",
                     "jugadas del bot OK", "partidas completas", "errores (motivo: cantidad)"], filas),
              "<h3>Objetivos (umbrales de k6)</h3>" + tabla_umbrales(res)]
    v = vent.get("bot")
    rec = recursos_en(recursos, v["inicio"] / 1000, v["fin"] / 1000) if v else None
    return "".join(partes), {"niveles": niveles, "p50": p50s, "p95": p95s, "okj": okj, "okp": okp,
                             "motivos": motivos, "rec": rec, "res": res}


def seccion_login(vent, intro):
    datos = leer_k6("login", {"http_reqs", "http_req_duration"})
    res = resumen("login")
    if res is None:
        return "<h2>Inicio de sesión</h2><p><i>Sin resultados.</i></p>", None
    t0 = min(t for t, *_ in datos["http_reqs"])
    ok_s, frenados = defaultdict(int), defaultdict(int)
    lat = defaultdict(list)
    for t, v, _, st, _ in datos["http_reqs"]:
        (ok_s if st == "200" else frenados)[t - t0] += 1
    for _, v, _, st, _ in datos["http_req_duration"]:
        lat[st].append(v)
    n = max(list(ok_s) + list(frenados)) + 1
    total_ok, total_429 = sum(ok_s.values()), sum(frenados.values())
    sostenida = max(0, total_ok - 21) / max(1, n)
    grafico = grafico_lineas("Inicios de sesión por segundo", [
        ("entraron (200)", C[2], [(x + 0.5, ok_s.get(x, 0)) for x in range(n)], False),
        ("frenados (429)", C[1], [(x + 0.5, frenados.get(x, 0)) for x in range(n)], False)], n, unidad="por s", alto=170)
    partes = ['<h2 class="pb">Inicio de sesión por encima del límite</h2>', intro, f'<div class="chart">{grafico}</div>',
              tabla(["Intentos", "entraron (200)", "frenados (429)", "tasa sostenida que entra", "latencia p95 de 200",
                     "latencia p95 de 429"],
                    [[fmt(total_ok + total_429), fmt(total_ok),
                      f"{fmt(total_429)} ({fmt(100 * total_429 / max(1, total_ok + total_429), 1)} %)",
                      f"{fmt(sostenida, 1)} /s", f"{fmt(pct(lat['200'], 95))} ms", f"{fmt(pct(lat['429'], 95))} ms"]]),
              "<h3>Objetivos (umbrales de k6)</h3>" + tabla_umbrales(res)]
    return "".join(partes), {"ok": total_ok, "frenados": total_429, "sostenida": sostenida,
                             "p95_200": pct(lat["200"], 95), "p95_429": pct(lat["429"], 95)}


# ======================================================================================= recursos y entorno


def seccion_recursos(info, recursos):
    partes = ['<h2 class="pb">Consumo de recursos</h2>', TEXTO["recursos_intro"]]
    carga = info.get("carga")
    if carga and carga["rec"]:
        t0 = carga["lt"]["t0"]
        rec = recursos_en(recursos, t0 + 70, t0 + 360)
        top = sorted(rec["contenedores"].items(), key=lambda kv: -kv[1]["media"])[:10]
        partes.append('<div class="chart">' + grafico_barras_h(
            "CPU media por contenedor con 40 usuarios estables (100 % = un núcleo)",
            [(n, c["media"], C[0]) for n, c in top], "%", fmt_valor=lambda v: fmt(v, 0)) + "</div>")
        memoria = sorted(rec["contenedores"].items(), key=lambda kv: -kv[1]["mem"])[:10]
        partes.append('<div class="chart">' + grafico_barras_h(
            "Memoria máxima por contenedor durante la carga",
            [(n, c["mem"], C[2]) for n, c in memoria], "MB", fmt_valor=lambda v: fmt(v, 0)) + "</div>")
    estres = info.get("estres")
    if estres and estres["rec"]:
        t0 = estres["lt"]["t0"]
        por_tramo = [(nombre, recursos_en(recursos, t0 + a, t0 + b)) for nombre, a, b in MESETAS["estres"]]
        nombres = sorted({n for _, r in por_tramo for n in r["contenedores"]},
                         key=lambda n: -max(r["contenedores"].get(n, {"media": 0})["media"] for _, r in por_tramo))[:10]
        filas = []
        for n in nombres:
            filas.append([f"<code>{esc(n)}</code>"] + [f"{fmt(r['contenedores'].get(n, {}).get('media'), 0)} %" for _, r in por_tramo])
        filas.append(["<b>CPU total de la máquina virtual de Docker</b>"] + [f"<b>{fmt(r['vm_media'], 0)} %</b>" for _, r in por_tramo])
        filas.append(["CPU del equipo (Windows)"] + [f"{fmt(sum(r['host']) / len(r['host']) if r['host'] else None, 0)} %" for _, r in por_tramo])
        filas.append(["CPU de k6 (generador de carga)"] + [f"{fmt(sum(r['k6']) / len(r['k6']) if r['k6'] else None, 0)} %" for _, r in por_tramo])
        partes.append("<h3>CPU media por tramo de la prueba de estrés</h3>")
        partes.append(tabla(["Contenedor"] + [nombre for nombre, *_ in MESETAS["estres"]], filas))
        partes.append('<p class="note">Contenedores: 100 % = un núcleo de los 12 que tiene la máquina virtual. '
                      'Máquina virtual: suma de los contenedores sobre 12 núcleos (100 % = todos). Equipo y k6: '
                      'porcentaje del total de núcleos de Windows.</p>')
        serie = serie_recursos(recursos, t0, t0 + estres["lt"]["duracion"], set(nombres[:4]))
        lineas = [(n, C[i], serie.get(n, []), False) for i, n in enumerate(nombres[:4])]
        partes.append('<div class="chart">' + grafico_lineas("CPU de los 4 contenedores más exigidos durante el estrés",
                                                              lineas, estres["lt"]["duracion"], unidad="% de un núcleo",
                                                              alto=190, bandas=BANDAS["estres"]) + "</div>")
    # Entorno: sonda y paginación por prueba
    filas = []
    for nombre in ("humo", "carga", "estres", "pico", "bot", "login"):
        d = info.get(nombre)
        rec = d and d.get("rec")
        if not rec:
            continue
        s = resumen_sonda(rec)
        filas.append([esc(nombre), fmt(s["n"]), f"{fmt(s['p50'])} ms", f"{fmt(s['max'])} ms",
                      f"{s['lentas']} ({fmt(100 * s['lentas'] / max(1, s['n']), 1)} %)",
                      fmt(rec["imposibles"]), f"{fmt(max(rec['paginacion']) / 1024 if rec['paginacion'] else None, 1)} GB",
                      f"{fmt(sum(rec['host']) / len(rec['host']) if rec['host'] else None, 0)} %"])
    partes.append("<h3>Salud del entorno durante cada prueba</h3>")
    partes.append(TEXTO["entorno_salud"])
    partes.append(tabla(["Prueba", "muestras de la sonda", "sonda p50", "sonda máx.", "sonda > 1 s o fallida",
                         "lecturas de CPU imposibles", "paginación máx.", "CPU media del equipo"], filas))
    return "".join(partes)


ENTORNO = [
    ("Equipo", "Laptop con Intel Core i7-10750H (6 núcleos, 12 hilos) y 15,9 GB de RAM, Windows 11"),
    ("Docker", "Docker Desktop 29.9.3 sobre WSL 2: la máquina virtual tiene 12 CPU y 7,7 GB de RAM"),
    ("Sistema probado", "22 contenedores de <code>compose.yaml</code>: 2 WAF (ModSecurity + OWASP CRS), 2 reverse proxies, "
                        "frontend SSR, 2 gateways, 9 servicios, 2 workers, RabbitMQ y 4 bases de datos"),
    ("Entradas", "Las mismas que los usuarios: <code>https://localhost:8443</code> (web) y <code>https://localhost:8444</code> "
                 "(app), con TLS 1.3 y el certificado validado (CA de mkcert instalada en Windows)"),
    ("Generador de carga", "k6 2.4.0 en el mismo equipo que el sistema"),
    ("Memoria libre al empezar", "2,0 GB de 15,9 GB, con 3,3 GB en el archivo de paginación (Edge 3,1 GB y VS Code 2,3 GB abiertos)"),
]

CSS = """
@page { size: A4; margin: 15mm 13mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.8pt; color: #1d1d1f; line-height: 1.42; }
h1 { font-size: 19pt; margin: 0 0 4px; }
.sub { color: #666; margin-bottom: 12px; }
h2 { font-size: 13.5pt; border-bottom: 2px solid #2a78d6; padding-bottom: 3px; margin-top: 16px; color: #1c5cab; }
h3 { font-size: 10.5pt; margin: 12px 0 4px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 8.5pt; }
th, td { border: 1px solid #ccc; padding: 3px 5px; text-align: left; vertical-align: top; }
th { background: #eef3fb; }
tr, .chart, pre { page-break-inside: avoid; }
code { font-family: Consolas, monospace; font-size: 8.2pt; background: #f3f3f3; padding: 0 2px; }
pre { font-family: Consolas, monospace; font-size: 8pt; background: #f6f6f6; border: 1px solid #ddd; padding: 6px; white-space: pre-wrap; }
.ok { color: #1a7f37; font-weight: 600; } .bad { color: #b42318; font-weight: 600; }
.box { background: #f2f7fd; border-left: 4px solid #2a78d6; padding: 6px 10px; margin: 8px 0; }
.warn { background: #fff7e8; border-left: 4px solid #eda100; padding: 6px 10px; margin: 8px 0; }
.note { font-size: 8.4pt; color: #555; margin: 2px 0 8px; }
.chart { margin: 6px 0; }
.pb { page-break-before: always; }
ul { margin: 4px 0 6px 18px; padding: 0; } li { margin: 2px 0; }
"""


def construir():
    vent = ventanas()
    recursos = leer_recursos()
    info, cuerpo = {}, []
    for nombre, titulo, umbral in (("humo", "Prueba de humo · 1 usuario web y 1 móvil, 1 min", None),
                                   ("carga", "Prueba de carga · 40 usuarios durante 5 min", (1000, "objetivo p95 páginas < 1 s")),
                                   ("estres", "Prueba de estrés · 50 → 100 → 200 → 300 usuarios", (1000, "objetivo p95 páginas < 1 s")),
                                   ("pico", "Prueba de pico · de 10 a 200 usuarios en 10 s", (1000, "objetivo p95 páginas < 1 s"))):
        html_sec, datos = seccion_prueba(nombre, titulo, TEXTO[f"{nombre}_intro"], recursos, vent, umbral)
        cuerpo.append(html_sec + TEXTO.get(f"{nombre}_analisis", ""))
        info[nombre] = datos
    html_bot, info["bot"] = seccion_bot(recursos, vent, TEXTO["bot_intro"])
    cuerpo.append(html_bot + TEXTO.get("bot_analisis", ""))
    html_login, info["login"] = seccion_login(vent, TEXTO["login_intro"])
    cuerpo.append(html_login + TEXTO.get("login_analisis", ""))
    # recursos del login y bot ya vienen en info; los de login no se calculan en seccion_login
    if vent.get("login"):
        info["login"] = dict(info.get("login") or {}, rec=recursos_en(recursos, vent["login"]["inicio"] / 1000, vent["login"]["fin"] / 1000))
    cuerpo.append(seccion_recursos(info, recursos))

    fecha = datetime.fromtimestamp(min(v["inicio"] for v in vent.values()) / 1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d") if vent else ""
    entorno = tabla(None, [[f"<b>{esc(k)}</b>", v] for k, v in ENTORNO])
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Pruebas de rendimiento con k6</title>
<style>{CSS}</style></head><body>
<h1>Pruebas de rendimiento de Insightful Games con k6</h1>
<div class="sub">Web y app móvil a través de los WAF y los reverse proxies · corrida del {fecha} · rama <code>feature/waf-compose-unico</code></div>
{TEXTO["resumen"]}
<h2>Objetivo y alcance</h2>{TEXTO["alcance"]}
<h2>Entorno</h2>{entorno}{TEXTO["entorno_nota"]}
<h2>Diseño de las pruebas</h2>{TEXTO["diseno"]}
{''.join(cuerpo)}
<h2 class="pb">Análisis</h2>{TEXTO["analisis"]}
<h2>Recomendaciones</h2>{TEXTO["recomendaciones"]}
<h2>Limitaciones</h2>{TEXTO["limitaciones"]}
<h2>Cómo repetir las pruebas</h2>{TEXTO["repetir"]}
</body></html>"""
    SALIDA.write_text(doc, encoding="utf-8")
    return info


if __name__ == "__main__":
    construir()
    print(SALIDA)
