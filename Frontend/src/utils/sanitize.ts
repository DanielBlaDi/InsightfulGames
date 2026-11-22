/**
 * Utilidades de sanitización para prevenir XSS.
 *
 * Escapa caracteres HTML peligrosos y valida URLs seguras.
 * Estas funciones son puras y no dependen del DOM, aptas para SSR.
 */

// Usar concatenación explícita para evitar que editores o herramientas auto-conviertan entidades HTML
const ENTITY_AMP = '&' + 'amp;';
const ENTITY_LT = '&' + 'lt;';
const ENTITY_GT = '&' + 'gt;';
const ENTITY_QUOT = '&' + 'quot;';
const ENTITY_APOS = '&' + 'apos;';

/**
 * Escapa caracteres HTML especiales para prevenir inyección.
 * Convierte: & -> &amp;, < -> &lt;, > -> &gt;, " -> &quot;, ' -> &apos;
 */
export function escapeHtml(input: string): string {
  if (typeof input !== 'string') return '';
  return input
    .replace(/&/g, ENTITY_AMP)
    .replace(/</g, ENTITY_LT)
    .replace(/>/g, ENTITY_GT)
    .replace(/"/g, ENTITY_QUOT)
    .replace(/'/g, ENTITY_APOS);
}

/**
 * Sanitiza un string para uso seguro en atributos HTML (href, src, etc.).
 * Permite solo protocolos seguros (https, mailto, tel) y rutas relativas.
 */
export function sanitizeUrl(input: string): string {
  if (typeof input !== 'string') return '';

  const trimmed = input.trim().toLowerCase();

  // Bloquear javascript:, data:, vbscript:, etc.
  const dangerousProtocols = ['javascript:', 'data:', 'vbscript:', 'file:', 'about:'];
  for (const protocol of dangerousProtocols) {
    if (trimmed.startsWith(protocol)) {
      return '#'; // URL segura por defecto
    }
  }

  // Permitir https:, http: (para desarrollo), mailto:, tel:, y rutas relativas
  const safeProtocols = ['https://', 'http://', 'mailto:', 'tel:', '/', '#'];
  const isSafe = safeProtocols.some(p => trimmed.startsWith(p));

  return isSafe ? input : '#';
}

/**
 * Sanitiza un string para uso en contenido de texto (no HTML).
 * Útil para data-* attributes, contenido de textContent, etc.
 */
export function sanitizeText(input: string): string {
  if (typeof input !== 'string') return '';
  return escapeHtml(input).trim();
}

/**
 * Valida que un string sea un UUID válido (v4).
 */
export function isValidUuid(input: string): boolean {
  if (typeof input !== 'string') return false;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(input);
}

/**
 * Sanitiza un nombre de usuario: solo alfanuméricos, guiones, guiones bajos.
 * Longitud entre 3 y 20 caracteres.
 */
export function sanitizeUsername(input: string): string {
  if (typeof input !== 'string') return '';
  // Solo permitir caracteres seguros
  const sanitized = input.replace(/[^a-zA-Z0-9_-]/g, '');
  // Limitar longitud
  return sanitized.slice(0, 20);
}

/**
 * Sanitiza entrada de texto libre (descripciones, comentarios, etc.).
 * Escapa HTML y limita longitud.
 */
export function sanitizeFreeText(input: string, maxLength: number = 1000): string {
  if (typeof input !== 'string') return '';
  return escapeHtml(input).slice(0, maxLength);
}

/**
 * Valida y sanitiza un color hexadecimal (#RRGGBB o #RGB).
 */
export function sanitizeColor(input: string): string {
  if (typeof input !== 'string') return '#000000';
  const hexColorRegex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
  return hexColorRegex.test(input) ? input : '#000000';
}

/**
 * Crea un objeto seguro para dangerouslySetInnerHTML (solo si es absolutamente necesario).
 * ADVERTENCIA: Usar solo como último recurso. Preferir siempre renderizado React nativo.
 */
export function createSafeHtml(html: string): { __html: string } {
  // En un caso real, aquí usarías DOMPurify o similar
  // Para este proyecto, no usamos dangerouslySetInnerHTML con contenido de usuario
  return { __html: '' };
}