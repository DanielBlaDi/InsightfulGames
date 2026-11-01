package com.insightfulgames.app.data.repository

import com.insightfulgames.app.data.model.BotRecord
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.model.Outcome
import com.insightfulgames.app.data.model.ProfileData
import com.insightfulgames.app.data.model.ProfileStats
import com.insightfulgames.app.data.model.RecentGame
import com.insightfulgames.app.data.model.StatsDto
import com.insightfulgames.app.data.remote.ApiService
import com.insightfulgames.app.data.remote.apiCall
import retrofit2.HttpException

/**
 * Estadísticas del perfil.
 *
 * 1. Intenta GET /users/me/stats (endpoint propuesto para el backend).
 * 2. Si el gateway responde 404 (aún no existe), las calcula desde GET /games.
 *    En ese caso el récord contra el bot (victorias/derrotas/tablas) solo se puede calcular
 *    si GET /games ya incluye playerColor; si no, queda en null y la UI lo indica.
 */
class StatsRepository(private val api: ApiService) {

    suspend fun load(): Result<ProfileData> = apiCall {
        val games = api.games()
        val remote = try {
            api.stats()
        } catch (e: HttpException) {
            if (e.code() == 404) null else throw e
        }
        ProfileData(
            stats = remote?.toDomain() ?: computeFromGames(games),
            // El backend devuelve la más reciente primero.
            recent = games.take(RECENT_LIMIT).map { it.toRecent() },
        )
    }

    private fun StatsDto.toDomain() = ProfileStats(
        totalGames = totalGames,
        finished = finished,
        inProgress = inProgress,
        localGames = byMode.local,
        botGames = byMode.vsBot,
        botRecord = BotRecord(vsBot.wins, vsBot.losses, vsBot.draws),
    )

    private fun computeFromGames(games: List<GameSummaryDto>): ProfileStats {
        val finishedBot = games.filter { it.mode == MODE_BOT && it.status == STATUS_FINISHED }
        val outcomes = finishedBot.map { it.outcome() }
        val record = if (outcomes.none { it == Outcome.UNKNOWN }) {
            BotRecord(
                wins = outcomes.count { it == Outcome.WIN },
                losses = outcomes.count { it == Outcome.LOSS },
                draws = outcomes.count { it == Outcome.DRAW },
            )
        } else {
            null
        }
        val finished = games.count { it.status == STATUS_FINISHED }
        return ProfileStats(
            totalGames = games.size,
            finished = finished,
            inProgress = games.size - finished,
            localGames = games.count { it.mode == MODE_LOCAL },
            botGames = games.count { it.mode == MODE_BOT },
            botRecord = record,
        )
    }

    private fun GameSummaryDto.toRecent() =
        RecentGame(gameId, mode, botLevel, createdAt, outcome())

    /** Resultado desde la perspectiva del usuario. */
    private fun GameSummaryDto.outcome(): Outcome = when {
        status != STATUS_FINISHED -> Outcome.IN_PROGRESS
        mode == MODE_LOCAL -> Outcome.LOCAL_FINISHED
        result == null || playerColor == null -> Outcome.UNKNOWN
        result == "draw" -> Outcome.DRAW
        result == playerColor -> Outcome.WIN
        else -> Outcome.LOSS
    }

    private companion object {
        const val RECENT_LIMIT = 10
        const val MODE_LOCAL = "local"
        const val MODE_BOT = "vs_bot"
        const val STATUS_FINISHED = "finished"
    }
}
