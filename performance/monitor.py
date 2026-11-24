"""Registra el consumo de recursos mientras corren las pruebas de rendimiento.

    pip install psutil
    python performance/monitor.py <salida.csv> <archivo-de-parada>

Cada ~3 s anota la CPU y la memoria de cada contenedor (docker stats), la CPU total del equipo y la de k6
(el generador de carga corre en la misma máquina que el sistema). Se detiene cuando existe <archivo-de-parada>.
En docker stats, 100 % de CPU = un núcleo completo.
"""

import csv
import json
import os
import re
import subprocess
import sys
import time

import psutil

UNIDADES = {"B": 1 / 2**20, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024, "kB": 1 / 1024, "MB": 1, "GB": 1024}


def megas(texto):
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", texto or "")
    return float(m.group(1)) * UNIDADES.get(m.group(2), 1) if m else 0.0


def main():
    salida, parada = sys.argv[1], sys.argv[2]
    nuevo = not os.path.exists(salida)
    procesos = {}
    psutil.cpu_percent(None)
    with open(salida, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["ts_ms", "origen", "nombre", "cpu_pct", "mem_mb"])
        while not os.path.exists(parada):
            inicio = time.time()
            r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            ts = int(time.time() * 1000)
            for linea in r.stdout.splitlines():
                try:
                    d = json.loads(linea)
                except ValueError:
                    continue
                cpu = float((d.get("CPUPerc") or "0").rstrip("%") or 0)
                w.writerow([ts, "contenedor", d.get("Name"), round(cpu, 2), round(megas(d.get("MemUsage", "").split("/")[0]), 1)])
            w.writerow([ts, "host", "cpu_total", psutil.cpu_percent(None), round(psutil.virtual_memory().used / 2**20, 1)])
            k6_cpu = 0.0
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower().startswith("k6"):
                    proc = procesos.setdefault(p.pid, p)
                    try:
                        k6_cpu += proc.cpu_percent(None) / psutil.cpu_count()
                    except psutil.Error:
                        pass
            w.writerow([ts, "host", "k6", round(k6_cpu, 2), ""])
            f.flush()
            time.sleep(max(0.0, 3 - (time.time() - inicio)))


if __name__ == "__main__":
    main()
