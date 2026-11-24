# Escenarios de seguridad del reverse proxy (táctica "resistir ataques")

`medir_resistencia.py` mide, contra el stack levantado, los tres escenarios de cada entrada (web
`:FRONTEND_HTTPS_PORT` y móvil `:MOBILE_HTTPS_PORT`, que son los WAF delante de los reverse proxies) y escribe
`resultados.json`:

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

Las entradas son HTTPS (Secure Channel, `docs/secure-channel-tls.md`): el script valida el certificado
público con la CA de `TLS_CA_FILE` (obligatoria) y nunca desactiva la verificación:

```powershell
$env:TLS_CA_FILE = "$(mkcert -CAROOT)\rootCA.pem"
python medir_resistencia.py
```

- El cliente legítimo de S1 corre dentro del contenedor `api-gateway-mobile` (otra IP para nginx) y entra
  directo a `https://reverse-proxy-mobile:8443` / `https://reverse-proxy-web:8443`. Esos proxies presentan el
  certificado interno, que valida con `INTERNAL_TLS_CA_FILE` (por defecto `certs/internal/ca/ca.crt`).
- En S2 cuentan como bloqueadas las respuestas 404 del proxy, 403 de las reglas del WAF y 400/405 del Nginx del
  WAF: ninguna llega a un gateway (se comprueba en sus logs).
- En S1, el límite de login lo aplica el proxy por IP. En Docker Desktop todo el tráfico del host llega al WAF
  con la IP de la red de Docker, así que el límite se comporta como global (ver `docs/secure-channel-tls.md`, 11.4).

Variables opcionales: `PROXY_HOST`, `PROXY_SCHEME` (`https` por defecto; `http` solo para un stack antiguo sin
TLS), `FRONTEND_HTTPS_PORT`, `MOBILE_HTTPS_PORT`, `TLS_CA_FILE`, `INTERNAL_TLS_CA_FILE`, `BRUTE_FORCE_ATTEMPTS`,
`LEGIT_CONTAINER`.
El informe con los diagramas y los resultados medidos está en `docs/escenarios-seguridad-reverse-proxy.pdf`.
