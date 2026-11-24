# Escenario S5: Rate Limiting en API Gateways

## Seguridad

- **Atributo:** Seguridad / disponibilidad.
- **Fuente:** Usuario autenticado que automatiza operaciones costosas.
- **Estímulo:** Una cuenta supera cinco solicitudes por 60 segundos sobre una operación protegida.
- **Artefacto:** API Gateway web y API Gateway móvil.
- **Entorno:** Docker Compose, con usuarios legítimos activos.
- **Respuesta:** `429 RATE_LIMIT_EXCEEDED`, encabezado `Retry-After`, sin llamadas posteriores.
- **Táctica:** limitar la tasa de eventos y rechazar carga excedente antes de consumir recursos.
- **Patrón:** Rate Limiting.
- **Algoritmo:** Sliding Window Log de marcas de tiempo por clave.

## Operaciones protegidas

| Gateway | Ruta |
|---|---|
| Web | `POST /games` |
| Web | `POST /tutor/analyses` |
| Móvil | `POST /games` |

La clave usa el `sub` validado del JWT. No se confía en `X-User-Id`. El contador es local a cada proceso del gateway y no se comparte entre replicas.

## Implementacion

El limitador esta en `Backend/Rate_limiting/escenario/rate_limit.py`. Los Dockerfiles de ambos gateways copian ese archivo junto al `main.py`. 

Los diagramas existentes deben actualizarse solo si documentan por separado los pasos internos de cada gateway o muestran sus respuestas HTTP. Basta anadir:

1. JWT validado.
2. Consulta al Sliding Window Log.
3. `429` si el contador excede cinco solicitudes.
4. Llamada al servicio posterior solo si se permite.

## Ejecutar pruebas

Desde la raiz:

```powershell
cd Backend\api-gateway
python -m pytest tests/test_tutor_flows.py -q

cd ..\api-gateway-mobile
python -m pytest tests/test_local_games.py -q
```

## Ejecutar medicion

Levantar el stack:

```powershell
docker compose up --build -d
```

Instalar dependencias y medir cinco repeticiones:

```powershell
python -m pip install httpx
cd Backend\Rate_limiting\escenario
python medir_rate_limit.py
```

El medidor genera `resultados.json` con estados HTTP, latencias y aislamiento entre usuarios.

## Reproducir el informe

El informe `.md` se mantiene en:

```text
docs/escenario-seguridad-rate-limit-gateways.md
```

No es necesario crear PDF para entregar este documento; el analisis debe completarse con `resultados.json`
y los resultados reales obtenidos contra Docker. Las pruebas TestClient no sustituyen esa medicion.

## Informe

El documento escrito de entrega debe conservar el formato utilizado por los escenarios de reverse proxy:

- fuente;
- estimulo;
- artefacto;
- entorno;
- respuesta;
- medidas y objetivos;
- medidos;
- repeticiones;
- limitaciones.

Los datos medidos deben guardarse en `Backend/Rate_limiting/escenario/resultados.json` y no deben sustituirse por valores inventados.

PDF recomendado:

```text
docs/escenarios-seguridad-rate-limit.pdf
```
