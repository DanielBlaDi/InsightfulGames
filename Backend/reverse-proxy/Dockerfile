# Reverse proxy (Reverse Proxy Pattern). Una imagen por entrada, elegida con ENTRY al construir:
#   ENTRY=web     -> reverse-proxy-web     escucha en 8000 (navegador: frontend + gateway web)
#   ENTRY=mobile  -> reverse-proxy-mobile  escucha en 8090 (app Android: gateway móvil)
# Imagen sin privilegios: Nginx corre como usuario "nginx", por eso usa puertos altos
# (el compose publica FRONTEND_PORT -> 8000 y MOBILE_GATEWAY_PORT -> 8090).
FROM nginxinc/nginx-unprivileged:1.27-alpine

ARG ENTRY=web
ARG HEALTH_PORT=8000

# conf.d se carga en orden alfabético: primero lo común (resolver, map, zona de rate-limit), luego el server.
COPY nginx/common.conf /etc/nginx/conf.d/00-common.conf
COPY nginx/${ENTRY}.conf /etc/nginx/conf.d/default.conf

ENV HEALTH_PORT=${HEALTH_PORT}
EXPOSE ${HEALTH_PORT}

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -q --spider "http://127.0.0.1:${HEALTH_PORT}/health" || exit 1
