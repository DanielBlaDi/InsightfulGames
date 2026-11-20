package com.prototipo.profile.service;

import java.util.regex.Pattern;

/** Identificadores del contrato: UUID en texto (sección 1). */
public final class Ids {

    /** userId que Game Logic pone en participants tras un borrado de cuenta (sección 11). */
    public static final String ANONYMOUS_USER = "00000000-0000-0000-0000-000000000000";

    private static final Pattern UUID = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$");

    private Ids() {
    }

    public static boolean isUuid(String value) {
        return value != null && UUID.matcher(value).matches();
    }
}
