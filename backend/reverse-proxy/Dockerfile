# Reverse proxy (Reverse Proxy Pattern + Secure Channel Pattern). Una imagen por entrada, elegida con ENTRY:
#   ENTRY=web     -> reverse-proxy-web     HTTPS 8443 (navegador: frontend + gateway web, WSS)
#                                          HTTP  8000 (/health, redirección HTTPS y /api/* bloqueado)
#   ENTRY=mobile  -> reverse-proxy-mobile  HTTPS 8443 (app Android: gateway móvil)
#                                          HTTP  8090 (solo /health interno; resto bloqueado, no se publica)
# Imagen sin privilegios: Nginx corre como usuario "nginx" (uid 101), por eso usa puertos altos.
#
# Certificado y clave NO van en la imagen: compose.yaml monta un directorio del host en /etc/nginx/certs
# (solo lectura) con tls.crt y tls.key. Sin ellos Nginx no arranca (fallo visible, nunca HTTP de reserva).
FROM nginxinc/nginx-unprivileged:1.27-alpine

ARG ENTRY=web
ARG HEALTH_PORT=8000

# conf.d se carga en orden alfabético: primero lo común (resolver, map, rate-limit, política TLS) y luego
# el server. El server es una plantilla: el entrypoint de la imagen la pasa por envsubst a conf.d/default.conf.
COPY nginx/common.conf /etc/nginx/conf.d/00-common.conf
COPY nginx/${ENTRY}.conf.template /etc/nginx/templates/default.conf.template

# Solo se sustituyen estas variables; $host, $request_uri, etc. son de Nginx y quedan intactas.
ENV NGINX_ENVSUBST_FILTER="^(PUBLIC_HTTPS_PORT|HSTS_MAX_AGE)$" \
    PUBLIC_HTTPS_PORT=443 \
    HSTS_MAX_AGE=0 \
    HEALTH_PORT=${HEALTH_PORT}

EXPOSE ${HEALTH_PORT} 8443

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -q --spider "http://127.0.0.1:${HEALTH_PORT}/health" || exit 1
