FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8090

WORKDIR /app

COPY api-gateway-mobile/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api-gateway-mobile/main.py .
COPY Rate_limiting/escenario/rate_limit.py .
COPY gateway-shared/orchestration orchestration

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8090

# El puerto sale de PORT (contrato 8.5); exec para que uvicorn reciba las señales.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
