package com.prototipo.auth.util;

import java.util.regex.Pattern;

/**
 * Utilidades de sanitización para prevenir XSS y validar entrada de usuario.
 *
 * Escapa caracteres HTML peligrosos y detecta patrones de inyección.
 */
public final class SanitizeUtil {

    private SanitizeUtil() {
        // Clase de utilidad, no instanciable
    }

    // Patrones peligrosos para XSS
    private static final Pattern[] XSS_PATTERNS = {
        Pattern.compile("<script\\b[^>]*>.*?</script>", Pattern.CASE_INSENSITIVE | Pattern.DOTALL),
        Pattern.compile("javascript:", Pattern.CASE_INSENSITIVE),
        Pattern.compile("on\\w+\\s*=", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<iframe\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<object\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<embed\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<form\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<input\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<meta\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("<link\\b", Pattern.CASE_INSENSITIVE),
        Pattern.compile("expression\\s*\\(", Pattern.CASE_INSENSITIVE),
        Pattern.compile("vbscript:", Pattern.CASE_INSENSITIVE),
        Pattern.compile("data:text/html", Pattern.CASE_INSENSITIVE)
    };

    /**
     * Detecta patrones comunes de XSS en el input.
     *
     * @param value el string a verificar
     * @return true si contiene patrones XSS, false en caso contrario
     */
    public static boolean containsXss(String value) {
        if (value == null) {
            return false;
        }
        String lower = value.toLowerCase();
        for (Pattern pattern : XSS_PATTERNS) {
            if (pattern.matcher(lower).find()) {
                return true;
            }
        }
        return false;
    }

    /**
     * Escapa caracteres HTML especiales para prevenir inyección.
     * Convierte: & -> &, < -> <, > -> >, " -> ", ' -> '
     *
     * @param input el string a escapar
     * @return string con caracteres HTML escapados
     */
    public static String escapeHtml(String input) {
        if (input == null) {
            return "";
        }
        return input
            .replace("&", "&")
            .replace("<", "<")
            .replace(">", ">")
            .replace("\"", """)
            .replace("'", "'");
    }

    /**
     * Sanitiza texto de entrada del usuario.
     *
     * - Detecta y rechaza patrones XSS
     * - Escapa HTML
     * - Limita longitud
     *
     * @param value el string a sanitizar
     * @param maxLength longitud máxima permitida
     * @return string sanitizado
     * @throws IllegalArgumentException si contiene XSS o excede la longitud
     */
    public static String sanitizeText(String value, int maxLength) {
        if (value == null) {
            throw new IllegalArgumentException("El valor no puede ser nulo");
        }

        // Detectar XSS antes de sanitizar
        if (containsXss(value)) {
            throw new IllegalArgumentException("Entrada contiene patrones no permitidos");
        }

        // Escapar HTML
        String escaped = escapeHtml(value);

        // Limitar longitud
        if (escaped.length() > maxLength) {
            throw new IllegalArgumentException("El texto excede el máximo de " + maxLength + " caracteres");
        }

        return escaped;
    }

    /**
     * Valida y sanitiza un nombre de usuario.
     * Solo permite alfanuméricos, guiones y guiones bajos.
     * Longitud entre 3 y 20 caracteres.
     *
     * @param username el nombre de usuario a validar
     * @return nombre de usuario sanitizado
     * @throws IllegalArgumentException si no es válido
     */
    public static String sanitizeUsername(String username) {
        if (username == null) {
            throw new IllegalArgumentException("El nombre de usuario no puede ser nulo");
        }

        // Detectar XSS
        if (containsXss(username)) {
            throw new IllegalArgumentException("El nombre de usuario contiene caracteres no permitidos");
        }

        // Solo permitir caracteres seguros: alfanuméricos, guión, guión bajo
        String sanitized = username.replaceAll("[^a-zA-Z0-9_-]", "");

        if (sanitized.length() < 3 || sanitized.length() > 20) {
            throw new IllegalArgumentException("El nombre de usuario debe tener entre 3 y 20 caracteres");
        }

        return sanitized;
    }

    /**
     * Valida que un string sea un UUID válido (v4).
     *
     * @param uuid el string a validar
     * @return true si es UUID válido, false en caso contrario
     */
    public static boolean isValidUuid(String uuid) {
        if (uuid == null) {
            return false;
        }
        String uuidRegex = "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$";
        return uuid.matches("(?i)" + uuidRegex);
    }

    /**
     * Sanitiza una URL para uso seguro en atributos href, src, etc.
     * Permite solo protocolos seguros (https, mailto, tel) y rutas relativas.
     *
     * @param url la URL a sanitizar
     * @return URL segura o "#" si no es segura
     */
    public static String sanitizeUrl(String url) {
        if (url == null) {
            return "#";
        }

        String trimmed = url.trim().toLowerCase();

        // Bloquear protocolos peligrosos
        String[] dangerousProtocols = {"javascript:", "data:", "vbscript:", "file:", "about:"};
        for (String protocol : dangerousProtocols) {
            if (trimmed.startsWith(protocol)) {
                return "#";
            }
        }

        // Permitir protocolos seguros y rutas relativas
        String[] safeProtocols = {"https://", "http://", "mailto:", "tel:", "/", "#"};
        boolean isSafe = false;
        for (String protocol : safeProtocols) {
            if (trimmed.startsWith(protocol)) {
                isSafe = true;
                break;
            }
        }

        return isSafe ? url : "#";
    }
}