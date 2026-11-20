-- Profile/Stats (contrato v9, sección 8). PostgreSQL, en UTC.
-- Los ids son UUID v4 en texto, igual que en Auth (VARCHAR(36)).

CREATE TABLE IF NOT EXISTS profiles (
    user_id    VARCHAR(36)              NOT NULL PRIMARY KEY,
    username   VARCHAR(20)              NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Contadores de partidas multiplayer con resultado.
CREATE TABLE IF NOT EXISTS stats (
    user_id      VARCHAR(36) NOT NULL PRIMARY KEY REFERENCES profiles (user_id) ON DELETE CASCADE,
    games_played INTEGER     NOT NULL DEFAULT 0,
    wins         INTEGER     NOT NULL DEFAULT 0,
    losses       INTEGER     NOT NULL DEFAULT 0,
    draws        INTEGER     NOT NULL DEFAULT 0
);

-- eventId ya aplicados: un evento repetido no suma dos veces.
CREATE TABLE IF NOT EXISTS processed_events (
    event_id     VARCHAR(36)              NOT NULL PRIMARY KEY,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Tabla interna, fuera de la lista de v9: usuarios cuya cuenta se borró. Evita que un
-- user.registered tardío vuelva a crear el perfil. Pendiente de validar en el contrato.
CREATE TABLE IF NOT EXISTS deleted_users (
    user_id    VARCHAR(36)              NOT NULL PRIMARY KEY,
    deleted_at TIMESTAMP WITH TIME ZONE NOT NULL
);
