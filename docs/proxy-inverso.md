# Proxy inverso (Reverse Proxy Pattern)

Prototipo 3, escenario de seguridad 2. Implementado con Nginx en `Backend/reverse-proxy/`.

## Qué hace

Hay **dos contenedores de proxy, uno por tipo de cliente**. Delante de cada uno hay un **WAF** (ModSecurity +
OWASP CRS), y los WAF son los únicos servicios que publican puertos. Los clientes nunca hablan con el frontend ni
con los gateways directamente:

```
Navegador ══HTTPS══► waf-web    ══HTTPS══► reverse-proxy-web    ──► frontend-component / api-gateway-component
Android   ══HTTPS══► waf-mobile ══HTTPS══► reverse-proxy-mobile ──► api-gateway-mobile
```

El TLS (de cliente a WAF y de WAF a proxy) y el WAF están descritos en `docs/secure-channel-tls.md`. Este documento
trata el enrutamiento y las reglas de los proxies.

| Contenedor | Cliente | Entrada (a través del WAF) | Destino interno |
|---|---|---|---|
| `reverse-proxy-web` | Navegador | `https://host:${FRONTEND_HTTPS_PORT}/` | `frontend-component:80` (páginas y estáticos) |
| | | `/api/*` | `api-gateway-component:8080/*` (se quita `/api`) |
| | | `/api/ws/*` | `api-gateway-component:8080/ws/*` (WebSocket, `wss://`) |
| `reverse-proxy-mobile` | App Android | `https://host:${MOBILE_HTTPS_PORT}/*` | `api-gateway-mobile:8090/*` |

Cada proxy escucha HTTPS en `8443` (lo que recibe del WAF) y HTTP solo para su healthcheck (`8000` web, `8090`
móvil); ninguno de esos puertos se publica. Cada contenedor carga solo la configuración de su entrada: si uno se
cae o recibe un ataque, el otro sigue funcionando.

### Archivos

| Archivo | Contenido |
|---|---|
| `nginx/common.conf` | Lo común: `resolver` de Docker, `server_tokens off`, el `map` del WebSocket, la zona de rate-limit `auth_zone` y la política TLS |
| `nginx/web.conf.template` | Los `server` de la entrada web (`listen 8443 ssl` y `listen 8000`) |
| `nginx/mobile.conf.template` | Los `server` de la entrada móvil (`listen 8443 ssl` y `listen 8090`) |
| `Dockerfile` | Una sola imagen base. El argumento `ENTRY` (`web` o `mobile`) elige qué plantilla se copia, y `HEALTH_PORT` el puerto del healthcheck |
| `Backend/waf/real-ip.conf` | Montado en los dos proxies: solo aceptan `X-Real-IP` si viene de un WAF |

En `compose.yaml`, los dos servicios usan el mismo contexto de build con `args` distintos y montan su certificado
interno (`INTERNAL_WEB_TLS_DIR`, `INTERNAL_MOBILE_TLS_DIR`) en solo lectura.

### Reglas del proxy, además del enrutamiento

- `/api/internal/*` (web) y `/internal/*` (móvil) responden 404 en el proxy, incluidas variantes como `/API/Internal`,
  `/api//internal` o `/api/%69nternal`. Los gateways ya no exponen ninguna ruta `/internal`, así que este bloqueo es
  defensa en profundidad. (Muchas de esas variantes ya las bloquea antes el WAF con 403.)
- Se descarta `X-User-Id` del cliente; solo lo pone el gateway tras validar el JWT.
- `Cookie`, `Set-Cookie`, `Origin` e `Idempotency-Key` pasan intactos. La sesión web y la validación de `Origin` del
  WebSocket siguen en el gateway.
- `client_max_body_size 1m`, `server_tokens off` y un límite de 10 peticiones/s por IP (ráfaga de 20) en login y
  registro. Cada contenedor tiene su propia zona, así que la web y la app llevan cupos separados. La IP es la que
  envía el WAF en `X-Real-IP` (ver la limitación en Docker Desktop en `docs/secure-channel-tls.md`, 11.4).
- Los destinos se resuelven por DNS de Docker en cada petición: si un contenedor se recrea, el proxy no necesita reiniciarse.

El servidor Express del frontend conserva su propio proxy `/api` (contrato 5.4.1). Con el proxy inverso delante ya
no se usa en producción, pero sirve para `npm run dev` y sus pruebas.

## Segmentación de red

`compose.yaml` define tres subredes. Cada contenedor solo ve a sus vecinos directos:

```
            Internet / host (FRONTEND_PORT, FRONTEND_HTTPS_PORT, MOBILE_HTTPS_PORT)
                              │
 ┌─ public_network 10.20.1.0/24 ──────────────────────────────────────────────┐
 │  waf-web .13 · waf-mobile .14 · reverse-proxy-web .11 · reverse-proxy-mobile .12 │
 └──────────────────────────────┬─────────────────────────────────────────────┘
 ┌─ private_api 10.20.2.0/24 (internal) ──────────────────────────────┐
 │  proxies · frontend-component · api-gateway-component · api-gateway-mobile │
 └──────────────────────────────┬────────────────────────────────────┘
 ┌─ private_back 10.20.3.0/24 (internal) ─────────────────────────────┐
 │  gateways · auth · game-logic · single-player · multiplayer · tutor │
 │  botcito ×2 · profile-stats · timeout-worker · analysis-worker      │
 │  rabbitmq · mongo ×2 · mysql · postgres                              │
 └────────────────────────────────────────────────────────────────────┘
```

- **Solo `public_network` tiene salida al exterior.** Las otras dos son `internal: true`: no tienen salida a
  internet y Docker no publica puertos de un contenedor que solo esté en ellas.
- **Los WAF solo están en `public_network`:** solo alcanzan a los proxies, nunca al frontend, a los gateways ni a
  los servicios.
- **Los proxies solo alcanzan al frontend y a los gateways.** Aunque se comprometa un proxy, no llega a Auth,
  Game Logic ni a las bases de datos.
- **Los gateways son el único puente** entre `private_api` y `private_back`. La regla de capas (cliente → WAF →
  proxy → gateways → servicios) la impone la red, no solo el código.
- Cada contenedor tiene una IP fija, útil para reglas de firewall, para `real-ip.conf` y para leer logs.

## Para el informe (sección Seguridad)

**Escenario 2.** Un atacante en Internet intenta tres cosas:
- alcanzar directamente los servicios internos (gateways, Auth, Game Logic) o las rutas `/internal/*`, para saltarse la validación de sesión;
- inyectar `X-User-Id` para suplantar a un usuario;
- probar contraseñas por fuerza bruta.

**Entorno:** sistema en operación normal, expuesto a Internet.

**Respuesta:** los únicos puntos accesibles son los dos WAF, y detrás de ellos los dos proxies. Entre los dos
bloquean `/internal/*` (y detrás ningún gateway expone esas rutas), descartan `X-User-Id` y limitan la frecuencia
de login. Además, la red impide que el WAF y los proxies lleguen a los servicios.

**Medida:** 0 puertos de servicios internos publicados; 100 % de las peticiones a `/internal/*` terminadas en el
borde (WAF o proxy); como máximo 10 intentos de login por segundo y por IP llegan a Auth. Los valores medidos
están en `docs/escenarios-seguridad-reverse-proxy.pdf` (script: `Backend/reverse-proxy/escenarios/medir_resistencia.py`).

**Tácticas aplicadas:**
- limitar la exposición: solo los WAF publican puertos; topología oculta;
- limitar el acceso: filtrado de rutas y cabeceras en el borde;
- limitar la tasa: rate-limit en login y registro;
- separar entidades: WAF y proxy separados por cliente, y subredes internas.

**Patrón:** Reverse Proxy, un proxy por tipo de cliente, detrás de un WAF por tipo de cliente. En la vista de
despliegue, los WAF están en `public_network` y los proxies en la DMZ (`public_network` + `private_api`), entre los
WAF y los nodos `frontend`, `api-gateway-component` y `api-gateway-mobile`.

## Cómo probarlo

Con el stack levantado y los certificados creados (`docs/secure-channel-tls.md`, sección 8):

```powershell
$ca = "$(mkcert -CAROOT)\rootCA.pem"
curl.exe --cacert $ca https://localhost:8443/health                     # 200, a través de waf-web
curl.exe --cacert $ca https://localhost:8443/api/internal/auth/login    # 404 del proxy (o 403 del WAF)
curl.exe --cacert $ca https://localhost:8444/internal/auth/login        # 404 del proxy (o 403 del WAF)
curl.exe -sI http://localhost:8080/                                     # 301 a HTTPS (FRONTEND_PORT=8080)
curl.exe http://localhost:8081/health                                   # falla: Auth no está publicado
docker exec reverse-proxy-web wget -qO- http://127.0.0.1:8090/health    # falla: el proxy web no atiende la entrada móvil
```

Si `curl.exe` se queja de la revocación del certificado (`CERT_TRUST_REVOCATION_STATUS_UNKNOWN`), añade
`--ssl-no-revoke`: los certificados de desarrollo no tienen lista de revocación.

La app Android usa `BASE_URL = https://10.0.2.2:8444/` (debug), que llega a `waf-mobile`. En release, `BASE_URL`
es el dominio HTTPS público.

**Depuración:** ningún servicio interno publica puertos (sus redes son `internal`). Para consultar un endpoint
interno, usa `docker compose exec` desde un contenedor de su red, p. ej.
`docker compose exec api-gateway-mobile python -c "import urllib.request as u; print(u.urlopen('http://auth-component:8081/health').read())"`.
