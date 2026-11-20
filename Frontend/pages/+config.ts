import type { Config } from 'vike/types';
import vikeReact from 'vike-react/config';

// Configuración común de todas las páginas (contrato técnico definitivo, 5.4.2). Por defecto cada
// página es una aplicación de una sola página: el servidor entrega el HTML con el <head> y React
// se monta en el navegador. Solo /estadisticas activa el renderizado en servidor
// (pages/estadisticas/+config.ts).
export default {
  extends: [vikeReact],
  ssr: false,
  lang: 'es',
  title: 'Insightful Games — Ajedrez, Go y Shogi con Tutor IA',
  favicon: '/favicon.svg',
  htmlAttributes: { class: 'scroll-smooth' },
  bodyAttributes: {
    class:
      'bg-background font-body-md text-on-surface antialiased selection:bg-primary-fixed selection:text-on-primary-fixed',
  },
} satisfies Config;
