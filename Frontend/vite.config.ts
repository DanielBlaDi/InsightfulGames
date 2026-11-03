import react from '@vitejs/plugin-react'
import vike from 'vike/plugin'
import { defineConfig } from 'vite'
import { isInternalApiPath } from './server/routes.js'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), vike()],

  // Solo para `npm run dev`. En producción el proxy lo hace server/index.js con las mismas reglas.
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // /api/internal/* nunca llega al gateway: Vite responde 404.
        bypass: (req) => (isInternalApiPath(req.url ?? '') ? false : undefined),
      },
    },
  },
})
