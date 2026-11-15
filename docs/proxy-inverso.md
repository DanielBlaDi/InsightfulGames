# Proxy inverso (Reverse Proxy Pattern)

Prototipo 3, escenario de seguridad 2. Implementado con Nginx en `Backend/reverse-proxy/`.

## Qué hace

Un único contenedor, `reverse-proxy`, es el **único servicio que publica puertos** al exterior. Los clientes nunca hablan con el frontend, el gateway web ni el gateway móvil directamente.

| Cliente | Entrada | Destino interno |
|---|---|---|
| Navegador | `http://host:${FRONTEND_PORT}/` | `frontend-component:80` (páginas y estáticos) |
| Navegador | `/api/*` | `api-gateway-component:8080/*` (se quita `/api`) |
| Navegador | `/api/ws/*` | `api-gateway-component:8080/ws/*` (WebSocket) |
| App Android | `http://host:${MOBILE_GATEWAY_PORT}/*` | `api-gateway-mobile:8090/*` |

Reglas del proxy, además del enrutamiento:

- `/api/internal/*` (web) y `/internal/*` (móvil) responden 404 en el borde, incluidas variantes como `/API/Internal`, `/api//internal` o `/api/%69nternal`.
- Se descarta `X-User-Id` del cliente; solo lo pone el gateway tras validar el JWT.
- `Cookie`, `Set-Cookie`, `Origin` e `Idempotency-Key` pasan intactos (la sesión web y la validación de `Origin` del WebSocket siguen en el gateway).
- `client_max_body_size 1m`, `server_tokens off` y límite de 10 peticiones/s por IP (ráfaga 20) en login y registro.
- Los destinos se resuelven por DNS de Docker en cada petición: si un contenedor se recrea, el proxy no necesita reiniciarse.

El servidor Express del frontend conserva su propio proxy `/api` (contrato 5.4.1). Con el proxy inverso delante ya no se usa en producción, pero sirve para `npm run dev` y sus pruebas.

## Para el informe (sección Seguridad)

**Escenario 2.** Un atacante en Internet intenta alcanzar directamente los servicios internos (gateways, Auth, Game Logic) o rutas `/internal/*` para saltarse la validación de sesión, o inyectar `X-User-Id` para suplantar a un usuario. Entorno: sistema en operación normal, expuesto a Internet. Respuesta: el único punto accesible es el proxy, que bloquea `/internal/*`, descarta `X-User-Id` y limita la frecuencia de login. Medida: 0 puertos de servicios internos publicados; 100 % de peticiones a `/internal/*` terminadas con 404 en el proxy.

**Tácticas aplicadas:** limitar exposición (un solo punto de entrada, topología oculta) y limitar acceso (filtrado de rutas y cabeceras en el borde).

**Patrón:** Reverse Proxy, un punto de entrada con dos servidores virtuales (web y móvil). Vista de despliegue: el nodo `reverse-proxy` queda entre los clientes y los nodos `frontend`, `api-gateway-component` y `api-gateway-mobile`.

## Cómo probarlo

```bash
docker compose up --build -d
curl -i  http://localhost:${FRONTEND_PORT}/health                    # 200, lo responde el proxy
curl -i  http://localhost:${FRONTEND_PORT}/api/internal/auth/login   # 404 desde el proxy
curl -i  http://localhost:${MOBILE_GATEWAY_PORT}/internal/auth/login # 404 desde el proxy
curl -i  http://localhost:8081/health                                # falla: Auth ya no está publicado
```

La app Android no cambia: `BASE_URL = http://10.0.2.2:8090/` (debug) apunta ahora al proxy. En release, `BASE_URL` es el dominio HTTPS del proxy.

Depuración saltándose el proxy: `docker compose -f compose.yaml -f compose.debug.yaml up -d` (puertos solo en 127.0.0.1).

## Qué queda para los otros escenarios

- **Secure Channel (escenario 1):** terminar TLS en este mismo proxy (`listen ... ssl`), poner `COOKIE_SECURE=true` y `WS_ALLOWED_ORIGINS=https://...`.
- **Network Segmentation (escenario 3):** hoy hay una sola red `app`. Con el proxy como único publicado, el paso natural es una red `dmz` (proxy, frontend y gateways) y otra `internal` (servicios y bases de datos).
