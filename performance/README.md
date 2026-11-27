# Pruebas de rendimiento (k6)

Pruebas de carga de la web y de la app móvil contra el stack levantado con `docker compose up -d`. Entran por las
mismas puertas que los usuarios: los WAF por HTTPS (`https://localhost:8443` web, `https://localhost:8444` app).
El informe con los resultados y su análisis está en `docs/pruebas-rendimiento-k6.pdf`.

## Requisitos

- k6 (`winget install GrafanaLabs.k6`).
- La CA de desarrollo instalada en Windows (`mkcert -install`, ver `docs/secure-channel-tls.md`): k6 valida el
  certificado contra el almacén del sistema y nunca desactiva la verificación.
- Python con `psutil` para el monitor de recursos (`pip install psutil`).

## Ejecutar

```powershell
.\performance\ejecutar.ps1                                  # toda la batería (~40 min)
.\performance\ejecutar.ps1 -Pruebas humo,carga              # solo algunas
.\performance\ejecutar.ps1 -Python .venv\Scripts\python.exe # un Python que tenga psutil
python performance\informe.py                               # performance\resultados\informe.html
msedge --headless --no-pdf-header-footer --print-to-pdf=docs\pruebas-rendimiento-k6.pdf performance\resultados\informe.html
```

Antes de cada prueba, `ejecutar.ps1` corre `k6/preparar.js`, que crea o reutiliza 50 usuarios (`perf_001` a
`perf_050`, contraseña `Rendimiento-2026!`), les deja al menos 3 partidas y guarda sus tokens. Va despacio porque
el login tiene un límite de 10 peticiones/s por IP.

## Pruebas

| Script | Prueba | Qué hace |
|---|---|---|
| `k6/flujos.js` con `-e PERFIL=humo` | Humo | 1 VU web y 1 móvil durante 1 min; todas las sesiones móviles juegan |
| `k6/flujos.js` con `-e PERFIL=carga` | Carga | 40 VUs durante 5 min |
| `k6/flujos.js` con `-e PERFIL=estres` | Estrés | 50 → 100 → 200 → 300 VUs, 2 min en cada nivel |
| `k6/flujos.js` con `-e PERFIL=pico` | Pico | de 10 a 200 VUs en 10 s, 1 min arriba y vuelta a 10 |
| `k6/bot-ws.js` | Bot | partidas contra el bot por WSS con 1, 2, 4, 8 y 12 partidas simultáneas |
| `k6/login-limite.js` | Login | 20 inicios de sesión/s desde una IP (por encima del límite de 10/s) |

En `flujos.js` el 60 % de los VUs navega la web (páginas SSR y la API del historial) y el 40 % usa la app (inicio,
historial, detalle, estadísticas y, en el 30 % de las sesiones, una partida local). Cada VU hace pausas de 1 a 3 s.
Variables: `WEB_URL`, `MOVIL_URL`, `WEB_ORIGIN`, `PROB_ESCRITURA`; en el bot, `JUGADAS`, `BOT_NIVEL`,
`CONCURRENCIA` (p. ej. `1,2,4`) y `DURACION_NIVEL`; en el login, `TASA`; en `preparar.js`, `CLAVE_USUARIOS` y `USUARIOS`.

## Resultados (`performance/resultados/`)

| Archivo | Contenido | En Git |
|---|---|---|
| `<prueba>-resumen.json` | Resumen de k6, con los umbrales cumplidos o no | Sí |
| `ventanas.json` | Inicio, fin y código de salida de cada prueba (99 = algún umbral no se cumplió) | Sí |
| `recursos.csv` | CPU y memoria por contenedor, CPU del equipo y de k6, paginación y sonda `/health` | Sí |
| `informe.html` | Informe generado por `informe.py` | Sí |
| `<prueba>.csv.gz` | Una fila por petición y métrica (datos crudos) | No |
| `usuarios.json` | Tokens de los usuarios de prueba (válidos 1 h) | No |

El texto de análisis del informe está en `informe_texto.py` y se escribió para la corrida documentada: si se
repiten las pruebas, los números y los gráficos se actualizan solos, pero el análisis hay que revisarlo.
