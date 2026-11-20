import type { Config } from 'vike/types';

// Única página con renderizado en servidor (5.4.3): el HTML sale del servidor con los datos.
export default {
  ssr: true,
  title: 'Estadísticas — Insightful Games',
} satisfies Config;
