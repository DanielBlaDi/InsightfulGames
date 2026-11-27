# Frontend web de Insightful Games

React 19 + TypeScript + Vite 8, servido por un solo proceso Node con Express y Vike (renderizado en
servidor de `/estadisticas`; el resto, aplicación de una sola página).

```bash
npm ci
npm run dev       # desarrollo en :5173, proxy /api y /api/ws a http://localhost:8080
npm run build     # tsc -b && vite build
API_GATEWAY_URL=http://localhost:8080 PORT=3000 npm start   # servidor de producción
npm test          # pruebas del servidor; requiere npm run build
npm run lint      # oxlint
```

Estructura, cómo agregar páginas, sesión con cookie y despliegue: [docs/frontend-vike.md](../docs/frontend-vike.md).
