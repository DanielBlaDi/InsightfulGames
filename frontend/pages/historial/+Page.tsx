import HistoryPage from '../../src/history/HistoryPage';

/**
 * /historial: aplicación de una sola página (ssr: false, valor común).
 * Pide GET /api/games con la cookie de sesión (sección 4.2 y 5.4.2).
 */
export default function Page() {
  return <HistoryPage />;
}

