package com.insightfulgames.app.data.model

import kotlinx.serialization.Serializable

// Contratos v9. Las claves desconocidas se ignoran (clocks, legalMoves, etc.).

// ---- Auth (secciones 5 y 7) ----

@Serializable
data class RegisterRequest(val username: String, val password: String)

@Serializable
data class RegisterResponse(val userId: String, val username: String)

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class UserDto(val userId: String, val username: String)

@Serializable
data class LoginResponse(
    val accessToken: String,
    /** Segundos de vida del token (3600). */
    val expiresIn: Long,
    val user: UserDto,
)

// ---- Error común: { "error": { "code", "message" } } ----

@Serializable
data class ApiErrorEnvelope(val error: ApiErrorBody? = null)

@Serializable
data class ApiErrorBody(val code: String? = null, val message: String? = null)

// ---- GET /profile/me ----

@Serializable
data class ProfileDto(
    val userId: String,
    val username: String,
    val createdAt: String? = null,
)

// ---- GET /stats/me (solo partidas multiplayer con resultado) ----

@Serializable
data class StatsDto(
    val gamesPlayed: Int = 0,
    val wins: Int = 0,
    val losses: Int = 0,
    val draws: Int = 0,
)

// ---- GET /games (GameSummary, sección 19) ----

@Serializable
data class GameSummaryDto(
    val gameId: String,
    /** local | vs_bot | multiplayer */
    val mode: String,
    /** Solo multiplayer; null en los demás modos. */
    val matchId: String? = null,
    /** waiting | in_progress | finished */
    val status: String,
    /** white | black | draw | null */
    val result: String? = null,
    val endReason: String? = null,
    /** Color del usuario que pide la lista. null en local. */
    val color: String? = null,
    val createdAt: String,
)

@Serializable
data class GamesPageDto(
    val items: List<GameSummaryDto> = emptyList(),
    /** Opaco. null cuando no hay más páginas. */
    val nextCursor: String? = null,
)

// ---- GET /home: cada sección es independiente y puede venir en null ----

@Serializable
data class HomeDto(
    val profile: ProfileDto? = null,
    val stats: StatsDto? = null,
    val recentGames: List<GameSummaryDto>? = null,
    val unavailable: List<String> = emptyList(),
)

// ---- GameState (sección 19): detalle de partida ----

@Serializable
data class ParticipantDto(val userId: String, val color: String)

@Serializable
data class TimeControlDto(val minutes: Int)

@Serializable
data class MoveDto(
    val ply: Int,
    val color: String,
    val san: String,
    val uci: String,
    val fenAfter: String? = null,
    val timestamp: String? = null,
)

@Serializable
data class GameStateDto(
    val gameId: String,
    val mode: String,
    val visibility: String = "private",
    val matchId: String? = null,
    val participants: List<ParticipantDto> = emptyList(),
    val botLevel: Int? = null,
    val timeControl: TimeControlDto? = null,
    val status: String,
    val turn: String? = null,
    val fen: String? = null,
    val initialFen: String? = null,
    val moves: List<MoveDto> = emptyList(),
    val version: Long = 0,
    val result: String? = null,
    val endReason: String? = null,
    val createdAt: String,
    val finishedAt: String? = null,
)
