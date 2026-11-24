"""Texto del informe de rendimiento (performance/informe.py).

Las partes de diseño, alcance y procedimiento son fijas. Las de resultados y análisis se escribieron para la corrida
documentada (2026-11-24) y hay que revisarlas si se repiten las pruebas.
"""

TEXTO = {}

TEXTO["alcance"] = """
<p>Medir cuánto tráfico aguanta la aplicación en este equipo antes de dejar de cumplir sus objetivos de tiempo de
respuesta, cómo se comporta ante subidas bruscas y qué componente se satura primero. Las peticiones entran por las
mismas puertas que los usuarios reales: los WAF por HTTPS, luego los reverse proxies, los gateways y los servicios.</p>
<table>
<tr><th>Se prueba</th><th>Cómo</th></tr>
<tr><td>Web (navegador)</td><td>Páginas con renderizado en el servidor (<code>/</code>, <code>/historial</code>, <code>/estadisticas</code>) y la API
que llama el navegador: perfil, estadísticas, historial (en paralelo, como el frontend) y detalle de una partida.</td></tr>
<tr><td>App Android</td><td>La API del gateway móvil: inicio (<code>/home</code>), historial, detalle, estadísticas y, en el 30 % de las sesiones,
una partida local corta (crear, 4 jugadas y rendirse).</td></tr>
<tr><td>Partidas contra el bot</td><td>Por WebSocket seguro (WSS), con 1, 2, 4, 8 y 12 partidas simultáneas.</td></tr>
<tr><td>Inicio de sesión</td><td>A 20 intentos/s desde una sola IP, por encima del límite de los reverse proxies.</td></tr>
</table>
<p><b>No se prueba:</b> el multijugador en línea (necesita dos jugadores coordinados por WebSocket), el análisis del
tutor (asíncrono), la descarga de JavaScript y CSS del frontend, ni la interfaz de la app Android.</p>
"""

TEXTO["diseno"] = """
<table>
<tr><th>Prueba</th><th>Usuarios virtuales (VUs)</th><th>Duración</th><th>Para qué</th></tr>
<tr><td>Humo</td><td>1 web + 1 móvil</td><td>1 min</td><td>Comprobar que todos los recorridos funcionan (todas las sesiones móviles juegan) y calentar el sistema.</td></tr>
<tr><td>Carga</td><td>0 → 40 en 1 min, 40 durante 5 min</td><td>6,5 min</td><td>Comportamiento con un uso normal sostenido.</td></tr>
<tr><td>Estrés</td><td>50 → 100 → 200 → 300, 2 min en cada nivel</td><td>12,5 min</td><td>Encontrar el nivel en que deja de cumplir los objetivos.</td></tr>
<tr><td>Pico</td><td>10 → 200 en 10 s, 1 min arriba, vuelta a 10</td><td>3 min</td><td>Reacción ante una subida brusca y recuperación.</td></tr>
<tr><td>Bot</td><td>1, 2, 4, 8 y 12 partidas, 90 s cada nivel</td><td>7,8 min</td><td>Capacidad del motor (Botcito) y del WebSocket.</td></tr>
<tr><td>Login</td><td>20 intentos/s (tasa constante)</td><td>1 min</td><td>Comprobar el límite de 10/s por IP de los reverse proxies.</td></tr>
</table>
<ul>
<li><b>Mezcla:</b> el 60 % de los VUs navega la web y el 40 % usa la app. Cada VU hace pausas de 1 a 3 s entre acciones
(tiempo de una persona leyendo o pensando), así que 40 VUs generan unas 30 peticiones/s, no 40.</li>
<li><b>Usuarios:</b> 50 cuentas de prueba (<code>perf_001</code> a <code>perf_050</code>) con al menos 3 partidas cada una.
Las sesiones se abren antes de cada prueba y despacio, porque el login tiene un límite de frecuencia que, si no,
frenaría la propia prueba.</li>
<li><b>Medición:</b> k6 registra cada petición. Un monitor anota cada 3 s la CPU y la memoria de cada contenedor, la CPU
del equipo y de k6, la memoria paginada de Windows y el tiempo de una sonda trivial (<code>/health</code>).</li>
</ul>
<h3>Objetivos (SLO) usados como umbrales</h3>
<table>
<tr><th>Métrica</th><th>Objetivo</th><th>Por qué</th></tr>
<tr><td>Peticiones fallidas</td><td>&lt; 1 %</td><td>Casi ninguna acción del usuario debe fallar.</td></tr>
<tr><td>Checks (respuesta correcta)</td><td>&gt; 99 %</td><td>Además del código HTTP, el contenido esperado.</td></tr>
<tr><td>p95 de páginas (SSR)</td><td>&lt; 1 s</td><td>Una página que tarda más de 1 s ya se percibe lenta.</td></tr>
<tr><td>p95 de lecturas de la API</td><td>&lt; 500 ms</td><td>Lo que el usuario espera al abrir el historial o el inicio.</td></tr>
<tr><td>p95 de escrituras (jugadas, crear, rendirse)</td><td>&lt; 800 ms</td><td>Una jugada debe sentirse inmediata.</td></tr>
<tr><td>p95 de la respuesta del bot</td><td>&lt; 3 s</td><td>Incluye ~0,5 s que el motor piensa a propósito.</td></tr>
<tr><td>Jugadas del bot que llegan</td><td>&gt; 99 %</td><td>Si el bot no responde, la partida queda bloqueada.</td></tr>
</table>
<p class="note">p50, p95 y p99: tiempo por debajo del cual queda el 50 %, el 95 % y el 99 % de las peticiones.</p>
"""

TEXTO["entorno_nota"] = """
<div class="warn"><b>Aviso sobre el entorno.</b> El sistema y el generador de carga corren en el mismo portátil, y al
empezar quedaban solo 2 GB de RAM libres. Se decidió hacer las pruebas igual y documentar el efecto: cuando Windows
se queda sin memoria pagina la máquina virtual de Docker y la congela por momentos, lo que aparece como peticiones
de varios segundos que no se deben a la aplicación. La sección «Salud del entorno» separa ese ruido usando una sonda
que no ejecuta nada de la aplicación.</div>
"""

TEXTO["humo_intro"] = "<p>Un usuario web y uno móvil durante un minuto; todas las sesiones móviles juegan una partida.</p>"
TEXTO["carga_intro"] = "<p>Uso normal sostenido: 40 usuarios simultáneos (24 en la web y 16 en la app) durante 5 minutos.</p>"
TEXTO["estres_intro"] = "<p>La carga sube por escalones hasta 300 usuarios simultáneos para ver dónde deja de cumplir los objetivos.</p>"
TEXTO["pico_intro"] = "<p>De 10 a 200 usuarios en 10 segundos, un minuto arriba y vuelta a 10 para medir la recuperación.</p>"
TEXTO["bot_intro"] = """<p>Cada usuario virtual crea una partida contra el bot (nivel 5), se conecta por WSS y juega 8 jugadas
legales al azar, pensando de 1 a 3 s cada una. Se mide desde que envía su jugada hasta que recibe la del bot.</p>"""
TEXTO["login_intro"] = """<p>20 inicios de sesión por segundo con credenciales correctas, todos desde el mismo equipo
(una IP), durante un minuto. El límite de los reverse proxies es 10/s por IP con ráfaga de 20.</p>"""

TEXTO["recursos_intro"] = """<p>CPU y memoria medidas por el monitor durante las pruebas. Muestran qué componente
trabaja más con cada nivel de carga.</p>"""

TEXTO["entorno_salud"] = """<p>La sonda pide <code>/health</code> a través del WAF cada 3 s; ese endpoint no toca la
aplicación, así que si tarda más de 1 s el retraso es del entorno. Una «lectura de CPU imposible» es una muestra de
<code>docker stats</code> por encima de 12 núcleos: ocurre cuando la máquina virtual se detuvo entre dos mediciones.</p>"""

TEXTO["repetir"] = """
<pre>winget install GrafanaLabs.k6             # una vez
pip install psutil                          # para el monitor de recursos
docker compose up -d                        # stack con los WAF y los certificados (docs/secure-channel-tls.md)
.\\performance\\ejecutar.ps1                 # toda la batería (~40 min); o -Pruebas carga,bot
python performance\\informe.py               # genera performance\\resultados\\informe.html
msedge --headless --no-pdf-header-footer --print-to-pdf=docs\\pruebas-rendimiento-k6.pdf performance\\resultados\\informe.html</pre>
<p>Los scripts de k6 están en <code>performance/k6/</code> y los resultados en <code>performance/resultados/</code>
(los CSV por petición y los tokens no se versionan).</p>
"""

for clave in ("resumen", "analisis", "recomendaciones", "limitaciones"):
    TEXTO.setdefault(clave, "<p><i>Pendiente.</i></p>")
