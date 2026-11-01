package com.insightfulgames.app.data.model

/** Sesión activa del usuario. */
data class Session(val token: String, val userId: String, val username: String)

/** Resultado de una partida desde el punto de vista del usuario. */
enum class Outcome { WIN, LOSS, DRAW, IN_PROGRESS, LOCAL_FINISHED, UNKNOWN }

data class BotRecord(val wins: Int, val losses: Int, val draws: Int) {
    val played: Int get() = wins + losses + draws
    val winRate: Double get() = if (played == 0) 0.0 else wins.toDouble() / played
}

data class ProfileStats(
    val totalGames: Int,
    val finished: Int,
    val inProgress: Int,
    val localGames: Int,
    val botGames: Int,
    /** null si el backend aún no permite saber quién ganó desde la perspectiva del usuario. */
    val botRecord: BotRecord?,
)

data class RecentGame(
    val gameId: String,
    val mode: String,
    val botLevel: Int?,
    val createdAt: String,
    val outcome: Outcome,
)

data class ProfileData(val stats: ProfileStats, val recent: List<RecentGame>)
