package com.prototipo.profile.util;

import java.util.regex.Pattern;

/**
 * Utilidades de sanitización para prevenir XSS y validar entrada de usuario.
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
     * Valida que un string sea un UUID válido (v4).
     */
    public static boolean isValidUuid(String uuid) {
        if (uuid == null) {
            return false;
        }
        String uuidRegex = "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$";
        return uuid.matches("(?i)" + uuidRegex);
    }
}