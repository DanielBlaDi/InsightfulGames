/**
 * Base del API Gateway, único destino de las llamadas del módulo (REST y WebSocket).
 * Sale de VITE_GATEWAY_URL (p. ej. http://localhost:8080); si no está definida se usa
 * el origen que sirve el frontend.
 */
export function gatewayBaseUrl(): string {
  const configured: string | undefined = import.meta.env.VITE_GATEWAY_URL;
  return (configured || window.location.origin).replace(/\/+$/, '');
}
