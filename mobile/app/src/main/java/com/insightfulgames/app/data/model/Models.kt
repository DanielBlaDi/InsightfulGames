package com.insightfulgames.app.data.model

/** Sesión activa del usuario. */
data class Session(val token: String, val userId: String, val username: String)

/** Estado de la sesión guardada en el teléfono. */
sealed interface SessionState {
    data object Loading : SessionState
    data object LoggedOut : SessionState
    data class LoggedIn(val session: Session) : SessionState
}

/**
 * Qué ruta pide el detalle (sección 5): local y vs_bot usan /games/{gameId};
 * multiplayer usa /matches/{matchId}, con el matchId que trae la lista.
 */
enum class DetailKind { GAME, MATCH }

data class DetailTarget(val kind: DetailKind, val id: String)

/** Resultado de una partida desde el punto de vista del usuario. */
enum class Outcome { WIN, LOSS, DRAW, WAITING, IN_PROGRESS, EXPIRED, NO_RESULT, WHITE_WON, BLACK_WON }
