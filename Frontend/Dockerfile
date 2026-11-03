# Frontend web (contrato técnico definitivo, 5.1 y 5.4.1): un solo proceso Node con Express y
# Vike en el puerto 80, sin Nginx. Variable obligatoria: API_GATEWAY_URL.

# Etapa 1: construcción (tsc + vite build con Vike)
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Etapa 2: ejecución, solo dependencias de producción
FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=builder /app/dist ./dist
COPY server ./server
# Sin root. Docker Engine 20.10 o superior permite a cualquier usuario abrir puertos bajos dentro
# del contenedor (net.ipv4.ip_unprivileged_port_start=0).
USER node
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -q --spider http://127.0.0.1/health || exit 1
CMD ["node", "server/index.js"]
