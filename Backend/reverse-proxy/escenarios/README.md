# Escenarios de seguridad del reverse proxy (táctica "resistir ataques")

`medir_resistencia.py` mide, contra el stack levantado, los tres escenarios de cada entrada del proxy
(web `:FRONTEND_HTTPS_PORT` y móvil `:MOBILE_HTTPS_PORT`) y escribe `resultados.json`:

| Escenario | Estímulo | Qué se mide |
| --- | --- | --- |
| S1 | Fuerza bruta: 300 logins con contraseña errónea desde una IP, lo más rápido posible | % frenado con 429 por nginx, intentos que llegan a Auth, latencia del 429, logins legítimos correctos desde otra IP durante el ataque |
| S2 | Acceso a lo interno: variantes de `/internal` (mayúsculas, `%69`, `..`, `//`, `;`) con un cliente HTTP crudo, y conexión TCP directa a los puertos de los servicios | % bloqueado, peticiones que aparecen en los logs de los gateways, puertos alcanzables desde el host |
| S3 | Suplantación: `X-User-Id` con el id de la víctima (cuatro grafías), con el token del atacante y sin token | Respuestas con datos de la víctima, respuestas sin token que dan 401 |

```bash
docker compose up -d
cd Backend/reverse-proxy/escenarios
python medir_resistencia.py          # necesita httpx y el CLI de docker
```

Con el Secure Channel (escenario 1, `docs/secure-channel-tls.md`) las entradas son HTTPS: el script valida el
certificado con la CA de `TLS_CA_FILE` (obligatoria) y nunca desactiva la verificación:

```powershell
$env:TLS_CA_FILE = "$(mkcert -CAROOT)\rootCA.pem"
python medir_resistencia.py
```

El cliente legítimo de S1 corre dentro del contenedor `api-gateway-mobile` (otra IP para nginx) y llega a
`https://reverse-proxy-mobile:8443` validando con la misma CA (por eso el certificado incluye ese nombre).
En el despliegue integrado (`-f compose.yaml -f Backend/waf/compose.waf.yaml`) las entradas públicas son los WAF y el proxy presenta
el certificado interno: define además `INTERNAL_TLS_CA_FILE=./certs/internal/ca/ca.crt` para ese cliente.
Las variantes de S2 que bloquee el WAF (403) cuentan como bloqueadas: nunca llegan a un gateway.
Variables opcionales: `PROXY_HOST`, `PROXY_SCHEME` (`https` por defecto; `http` para un stack sin TLS),
`FRONTEND_HTTPS_PORT`, `MOBILE_HTTPS_PORT` (o `FRONTEND_PORT` y `MOBILE_GATEWAY_PORT` con `http`),
`TLS_CA_FILE`, `INTERNAL_TLS_CA_FILE`, `BRUTE_FORCE_ATTEMPTS`, `LEGIT_CONTAINER`.
El informe con los diagramas y los resultados medidos está en `docs/escenarios-seguridad-reverse-proxy.pdf`.
