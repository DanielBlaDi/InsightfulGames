# Proxy inverso (Reverse Proxy Pattern)

Prototipo 3, escenario de seguridad 2. Implementado con Nginx en `Backend/reverse-proxy/`.

## Qué hace

Hay **dos contenedores de proxy, uno por tipo de cliente**. Junto con el WAF cuando se active, son los **únicos
servicios que publican puertos** al exterior. Los clientes nunca hablan con el frontend ni con los gateways directamente.

| Contenedor | Cliente | Entrada | Destino interno |
|---|---|---|---|
| `reverse-proxy-web` | Navegador | `https://host:${FRONTEND_HTTPS_PORT}/` | `frontend-component:80` (páginas y estáticos) |
| | | `/api/*` | `api-gateway-component:8080/*` (se quita `/api`) |
| | | `/api/ws/*` | `api-gateway-component:8080/ws/*` (WebSocket) |
| `reverse-proxy-mobile` | App Android | `https://host:${MOBILE_HTTPS_PORT}/*` | `api-gateway-mobile:8090/*` |

Cada contenedor carga solo la configuración de su entrada: el proxy web no escucha en 8090 y el móvil no escucha en 8000.
Si uno se cae o recibe un ataque, el otro sigue funcionando.

### Archivos

| Archivo | Contenido |
|---|---|
| `nginx/common.conf` | Lo común: `resolver` de Docker, `server_tokens off`, el `map` del WebSocket y la zona de rate-limit `auth_zone` |
| `nginx/web.conf` | El `server` de la entrada web (`listen 8000`) |
| `nginx/mobile.conf` | El `server` de la entrada móvil (`listen 8090`) |
| `Dockerfile` | Una sola imagen base. El argumento `ENTRY` (`web` o `mobile`) elige qué `server` se copia, y `HEALTH_PORT` el puerto del healthcheck |

En `compose.yaml`, los dos servicios usan el mismo contexto de build con `args` distintos.

### Reglas del proxy, además del enrutamiento

- `/api/internal/*` (web) y `/internal/*` (móvil) responden 404 en el borde, incluidas variantes como `/API/Internal`,
  `/api//internal` o `/api/%69nternal`. Los gateways ya no exponen ninguna ruta `/internal`, así que este bloqueo es
  defensa en profundidad.
- Se descarta `X-User-Id` del cliente; solo lo pone el gateway tras validar el JWT.
- `Cookie`, `Set-Cookie`, `Origin` e `Idempotency-Key` pasan intactos. La sesión web y la validación de `Origin` del
  WebSocket siguen en el gateway.
- `client_max_body_size 1m`, `server_tokens off` y un límite de 10 peticiones/s por IP (ráfaga de 20) en login y
  registro. Cada contenedor tiene su propia zona, así que la web y la app llevan cupos separados.
- Los destinos se resuelven por DNS de Docker en cada petición: si un contenedor se recrea, el proxy no necesita reiniciarse.

El servidor Express del frontend conserva su propio proxy `/api` (contrato 5.4.1). Con el proxy inverso delante ya
no se usa en producción, pero sirve para `npm run dev` y sus pruebas.

## Segmentación de red

`compose.yaml` define tres subredes. Cada contenedor solo ve a sus vecinos directos:

```
            Internet / host (HTTPS publicado en los WAF)
                              │
 ┌─ public_network 10.20.1.0/24 ─────────────────────────────────────┐
 │  (waf-component .10, comentado) · reverse-proxy-web .11 · reverse-proxy-mobile .12 │
 └──────────────────────────────┬────────────────────────────────────┘
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
- **Los proxies solo alcanzan al frontend y a los gateways.** Aunque se comprometa un proxy, no llega a Auth,
  Game Logic ni a las bases de datos.
- **Los gateways son el único puente** entre `private_api` y `private_back`. La regla de capas (cliente → proxy →
  gateways → servicios) la impone la red, no solo el código.
- Cada contenedor tiene una IP fija, útil para reglas de firewall y para leer logs.
- **WAF:** `waf-web` y `waf-mobile` publican los puertos de entrada y reenvían tráfico por TLS a sus proxies en `public_network`.

## Para el informe (sección Seguridad)

**Escenario 2.** Un atacante en Internet intenta tres cosas:
- alcanzar directamente los servicios internos (gateways, Auth, Game Logic) o las rutas `/internal/*`, para saltarse la validación de sesión;
- inyectar `X-User-Id` para suplantar a un usuario;
- probar contraseñas por fuerza bruta.

**Entorno:** sistema en operación normal, expuesto a Internet.

**Respuesta:** los únicos puntos accesibles son los dos proxies. Bloquean `/internal/*` (y detrás ningún gateway
expone esas rutas), descartan `X-User-Id` y limitan la frecuencia de login. Además, la red impide que los proxies
lleguen a los servicios.

**Medida:** 0 puertos de servicios internos publicados; 100 % de las peticiones a `/internal/*` terminadas en el proxy;
como máximo 10 intentos de login por segundo y por IP llegan a Auth. Los valores medidos están en
`docs/escenarios-seguridad-reverse-proxy.pdf` (script: `Backend/reverse-proxy/escenarios/medir_resistencia.py`).

**Tácticas aplicadas:**
- limitar la exposición: dos puntos de entrada y topología oculta;
- limitar el acceso: filtrado de rutas y cabeceras en el borde;
- limitar la tasa: rate-limit en login y registro;
- separar entidades: proxies separados por cliente y subredes internas.

**Patrón:** Reverse Proxy, un proxy por tipo de cliente. En la vista de despliegue, los nodos `reverse-proxy-web` y
`reverse-proxy-mobile` quedan en la DMZ (`public_network` + `private_api`), entre los clientes y los nodos
`frontend`, `api-gateway-component` y `api-gateway-mobile`.

## Cómo probarlo

```bash
docker compose up --build -d
curl -i "http://localhost:${FRONTEND_PORT}/health"
curl -i "https://localhost:${FRONTEND_HTTPS_PORT}/health"
curl -i "https://localhost:${MOBILE_HTTPS_PORT}/health"
```

En el emulador Android, la URL base usa HTTPS hacia el WAF móvil (por ejemplo, `https://10.0.2.2:8444/`).

Para consultar un endpoint interno durante la depuración, usa `docker compose exec` desde un contenedor de su red.
