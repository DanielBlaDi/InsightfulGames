# Escenarios de seguridad del reverse proxy (táctica "resistir ataques")

`medir_resistencia.py` mide, contra el stack levantado, los tres escenarios de cada entrada del proxy
(web `:FRONTEND_PORT` y móvil `:MOBILE_GATEWAY_PORT`) y escribe `resultados.json`:

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

El cliente legítimo de S1 corre dentro del contenedor `api-gateway-mobile` (otra IP para nginx). Variables opcionales:
`PROXY_HOST`, `FRONTEND_PORT`, `MOBILE_GATEWAY_PORT`, `BRUTE_FORCE_ATTEMPTS`, `LEGIT_CONTAINER`.
El informe con los diagramas y los resultados medidos está en `docs/escenarios-seguridad-reverse-proxy.pdf`.
