# Escenario S5: Rate Limiting en los API Gateways

## Escenario de seguridad

- **Atributo:** Seguridad / disponibilidad.
- **Fuente:** Usuario autenticado que automatiza solicitudes.
- **Estimulo:** Excede cinco solicitudes costosas en una ventana de 60 segundos.
- **Artefacto:** API Gateway web y API Gateway móvil.
- **Entorno:** Sistema Docker Compose en operación normal.
- **Respuesta:** `429 RATE_LIMIT_EXCEEDED` y `Retry-After`, sin invocar un servicio posterior.
- **Patron:** Rate Limiting.
- **Tactica:** limitar la tasa de eventos y rechazar carga excedente antes de consumir recursos internos.

## Implementacion

La implementacion autonoma esta en [Backend/Rate_limiting/escenario/rate_limit.py]Usa una ventana deslizante por combinacion de operación y `sub` del JWT.

Las rutas protegidas son:

| Gateway | Operacion |
|---|---|
| Web | `POST /games` |
| Web | `POST /tutor/analyses` |
| Movil | `POST /games` |

El limitador se inicializa en el lifespan de cada gateway y se consulta inmediatamente despues de validar el usuario autenticado.

## Medicion

La medicion debe ejecutarse contra Docker, no solamente con TestClient. El procedimiento completo esta en [README del escenario].

## Verificacion implementada

La verificacion automatizada valida que el limitador se integra en las rutas costosas:

| Gateway | Prueba | Resultado |
|---|---|---|
| Web | Tutor: cinco solicitudes permitidas y la sexta rechazada con 429 | 54 pruebas Tutor pasaron |
| Movil | Creacion de partida: cinco solicitudes permitidas y la sexta rechazada con 429 | 28 pruebas de partidas locales pasaron |

Los resultados unitarios confirman el comportamiento de respuesta y que el exceso no llega al flujo de `Game Logic` o `Tutor`. No miden latencia de Docker ni trafico de red real.

## Analisis esperado

El limite se considera cumplido si:

- las primeras cinco solicitudes aceptadas llegan a los servicios posteriores;
- la sexta solicitud recibe 429;
- el 429 incluye `Retry-After`;
- otro usuario conserva su propia cuota;
- una solicitud posterior permitida vuelve a pasar despues de la ventana;
- no hay llamadas posteriores a la operacion costosa para los excesos.

Estos criterios deben registrar datos reales en `Backend/Rate_limiting/escenario/resultados.json` antes de afirmarse como medicion final.

Medidas propuestas:

- solicitud aceptada frente a `429`;
- solicitudes que llegan a Game Logic o Tutor;
- latencia p50/p95;
- operaciones permitidas a otro usuario mientras el atacante esta bloqueado;
- restablecimiento de la cuota despues de 60 segundos;
- variacion entre cinco corridas.
