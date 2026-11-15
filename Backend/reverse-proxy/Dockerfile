# Proxy inverso (Reverse Proxy Pattern): único punto de entrada para el frontend web y la app móvil.
# Imagen sin privilegios: Nginx corre como usuario "nginx" y por eso escucha en 8000 y 8090
# (el compose publica FRONTEND_PORT -> 8000 y MOBILE_GATEWAY_PORT -> 8090).
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8000 8090

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -q --spider http://127.0.0.1:8000/health || exit 1
