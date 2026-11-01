package com.insightfulgames.app.ui

import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.model.MoveDto
import com.insightfulgames.app.data.model.Outcome
import com.insightfulgames.app.data.model.ParticipantDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class GameLabelsTest {

    private fun summary(
        mode: String = "multiplayer",
        matchId: String? = null,
        status: String = "finished",
        result: String? = null,
        endReason: String? = null,
        color: String? = null,
    ) = GameSummaryDto(
        gameId = "game-1", mode = mode, matchId = matchId, status = status,
        result = result, endReason = endReason, color = color, createdAt = "2026-10-29T15:00:00Z",
    )

    // ---- detalle: gameId para local/vs_bot, matchId para multiplayer ----

    @Test fun localAndBotOpenByGameId() {
        listOf("local", "vs_bot").forEach { mode ->
            val t = GameLabels.detailTarget(summary(mode = mode))
            assertEquals(DetailKind.GAME, t.kind)
            assertEquals("game-1", t.id)
        }
    }

    @Test fun multiplayerOpensByMatchId() {
        val t = GameLabels.detailTarget(summary(mode = "multiplayer", matchId = "match-9"))
        assertEquals(DetailKind.MATCH, t.kind)
        assertEquals("match-9", t.id)
    }

    // ---- resultado desde el punto de vista del usuario ----

    @Test fun winLossDraw() {
        assertEquals(Outcome.WIN, GameLabels.outcome(summary(result = "white", color = "white", endReason = "checkmate")))
        assertEquals(Outcome.LOSS, GameLabels.outcome(summary(result = "black", color = "white", endReason = "timeout")))
        assertEquals(Outcome.DRAW, GameLabels.outcome(summary(result = "draw", color = "black", endReason = "stalemate")))
    }

    @Test fun localHasNoUserColor() {
        assertEquals(Outcome.WHITE_WON, GameLabels.outcome(summary(mode = "local", result = "white", endReason = "checkmate")))
        assertEquals(Outcome.BLACK_WON, GameLabels.outcome(summary(mode = "local", result = "black", endReason = "surrender")))
    }

    @Test fun waitingInProgressAndExpired() {
        assertEquals(Outcome.WAITING, GameLabels.outcome(summary(status = "waiting")))
        assertEquals(Outcome.IN_PROGRESS, GameLabels.outcome(summary(status = "in_progress")))
        assertEquals(Outcome.EXPIRED, GameLabels.outcome(summary(result = null, endReason = "expired", color = "white")))
        assertEquals(Outcome.NO_RESULT, GameLabels.outcome(summary(result = null, endReason = "checkmate")))
    }

    // ---- jugadores ----

    private fun state(
        mode: String,
        participants: List<ParticipantDto>,
        botLevel: Int? = null,
    ) = GameStateDto(
        gameId = "g", mode = mode, participants = participants, botLevel = botLevel,
        status = "finished", createdAt = "2026-10-29T15:00:00Z",
    )

    @Test fun botIsNotAParticipant() {
        val g = state("vs_bot", listOf(ParticipantDto("me", "white")), botLevel = 8)
        assertEquals("Tú", GameLabels.playerLabel(g, "white", "me"))
        assertEquals("Botcito (nivel 8)", GameLabels.playerLabel(g, "black", "me"))
    }

    @Test fun multiplayerRivalDeletedAndWaiting() {
        val g = state("multiplayer", listOf(ParticipantDto("me", "white"), ParticipantDto(GameLabels.ANONYMOUS_USER_ID, "black")))
        assertEquals("Cuenta eliminada", GameLabels.playerLabel(g, "black", "me"))

        val rival = state("multiplayer", listOf(ParticipantDto("me", "white"), ParticipantDto("other", "black")))
        assertEquals("Rival", GameLabels.playerLabel(rival, "black", "me"))

        val waiting = state("multiplayer", listOf(ParticipantDto("me", "white")))
        assertEquals("Esperando rival", GameLabels.playerLabel(waiting, "black", "me"))
    }

    // ---- jugadas ----

    @Test fun movesText() {
        val moves = listOf(
            MoveDto(1, "white", "e4", "e2e4"),
            MoveDto(2, "black", "e5", "e7e5"),
            MoveDto(3, "white", "Nf3", "g1f3"),
        )
        assertEquals("1. e4 e5 2. Nf3", GameLabels.movesText(moves))
        assertEquals("", GameLabels.movesText(emptyList()))
    }

    @Test fun endReasonLabels() {
        assertEquals("Jaque mate", GameLabels.endReasonLabel("checkmate"))
        assertEquals("Abandono", GameLabels.endReasonLabel("abandonment"))
        assertNull(GameLabels.endReasonLabel(null))
    }
}
