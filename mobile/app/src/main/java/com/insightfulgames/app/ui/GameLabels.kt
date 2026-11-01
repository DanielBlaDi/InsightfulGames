package com.insightfulgames.app.ui

import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.DetailTarget
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.model.MoveDto
import com.insightfulgames.app.data.model.Outcome

/** Lógica de presentación sin dependencias de Android (se prueba con JUnit). */
object GameLabels {
    /** userId que Game Logic pone cuando se borra una cuenta (sección 11 del contrato). */
    const val ANONYMOUS_USER_ID = "00000000-0000-0000-0000-000000000000"

    fun modeLabel(mode: String): String = when (mode) {
        "local" -> "Local (dos jugadores)"
        "vs_bot" -> "Contra Botcito"
        "multiplayer" -> "Multijugador online"
        else -> mode
    }

    /**
     * Local y vs_bot se abren con /games/{gameId}; multiplayer con /matches/{matchId},
     * usando el matchId que trae la lista.
     */
    fun detailTarget(game: GameSummaryDto): DetailTarget =
        if (game.mode == "multiplayer" && game.matchId != null) {
            DetailTarget(DetailKind.MATCH, game.matchId)
        } else {
            DetailTarget(DetailKind.GAME, game.gameId)
        }

    /** Resultado desde el punto de vista del usuario. [color] es null en partidas locales y en el detalle. */
    fun outcome(
        status: String,
        result: String?,
        endReason: String?,
        color: String?,
    ): Outcome = when {
        status == "waiting" -> Outcome.WAITING
        status != "finished" -> Outcome.IN_PROGRESS
        endReason == "expired" -> Outcome.EXPIRED
        result == null -> Outcome.NO_RESULT
        result == "draw" -> Outcome.DRAW
        color == null -> if (result == "white") Outcome.WHITE_WON else Outcome.BLACK_WON
        result == color -> Outcome.WIN
        else -> Outcome.LOSS
    }

    fun outcome(game: GameSummaryDto): Outcome =
        outcome(game.status, game.result, game.endReason, game.color)

    fun outcome(game: GameStateDto): Outcome =
        outcome(game.status, game.result, game.endReason, color = null)

    fun outcomeLabel(outcome: Outcome): String = when (outcome) {
        Outcome.WIN -> "Victoria"
        Outcome.LOSS -> "Derrota"
        Outcome.DRAW -> "Tablas"
        Outcome.WAITING -> "Esperando rival"
        Outcome.IN_PROGRESS -> "En curso"
        Outcome.EXPIRED -> "Invitación caducada"
        Outcome.NO_RESULT -> "Sin resultado"
        Outcome.WHITE_WON -> "Ganaron blancas"
        Outcome.BLACK_WON -> "Ganaron negras"
    }

    fun endReasonLabel(endReason: String?): String? = when (endReason) {
        "checkmate" -> "Jaque mate"
        "stalemate" -> "Ahogado"
        "surrender" -> "Rendición"
        "draw" -> "Tablas acordadas"
        "timeout" -> "Tiempo agotado"
        "abandonment" -> "Abandono"
        "expired" -> "Caducada sin rival"
        else -> null
    }

    fun colorLabel(color: String): String = if (color == "white") "Blancas" else "Negras"

    /** Quién juega con [color]. En vs_bot el bot no es participante. */
    fun playerLabel(game: GameStateDto, color: String, myUserId: String): String {
        val p = game.participants.firstOrNull { it.color == color }
        return when {
            p != null && p.userId == myUserId -> "Tú"
            p != null && p.userId == ANONYMOUS_USER_ID -> "Cuenta eliminada"
            p != null -> "Rival"
            game.mode == "vs_bot" -> game.botLevel?.let { "Botcito (nivel $it)" } ?: "Botcito"
            else -> "Esperando rival"
        }
    }

    fun timeControlLabel(game: GameStateDto): String =
        game.timeControl?.let { "${it.minutes} min por bando" } ?: "Sin reloj"

    fun visibilityLabel(visibility: String): String =
        if (visibility == "shared") "Compartida" else "Privada"

    /** "1. e4 e5 2. Nf3 Nc6" */
    fun movesText(moves: List<MoveDto>): String = buildString {
        moves.forEachIndexed { i, m ->
            val number = (m.ply + 1) / 2
            if (m.color == "white") append("$number. ") else if (i == 0) append("$number... ")
            append(m.san)
            append(' ')
        }
    }.trim()
}
