package com.insightfulgames.app.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---- Auth (POST /auth/login en el Gateway) ----

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class UserDto(val userId: String, val username: String)

@Serializable
data class LoginResponse(
    val accessToken: String,
    /** Segundos de vida del token (hoy 3600). */
    val expiresIn: Long,
    val user: UserDto,
)

// ---- Errores: { "error": { "code": "...", "message": "..." } } ----

@Serializable
data class ApiErrorEnvelope(val error: ApiErrorBody? = null)

@Serializable
data class ApiErrorBody(val code: String? = null, val message: String? = null)

// ---- GET /games ----
// Hoy el backend solo devuelve gameId, mode, status, result y createdAt.
// Los campos opcionales de abajo llegarán cuando se amplíe GameSummary (ver README).

@Serializable
data class GameSummaryDto(
    val gameId: String,
    val mode: String,
    val status: String,
    val result: String? = null,
    val createdAt: String,
    val playerColor: String? = null,
    val botLevel: Int? = null,
    val endReason: String? = null,
    val finishedAt: String? = null,
)

// ---- GET /users/me/stats (endpoint PROPUESTO, aún no existe en el backend) ----

@Serializable
data class StatsDto(
    val totalGames: Int,
    val finished: Int,
    val inProgress: Int,
    val byMode: ByModeDto = ByModeDto(),
    val vsBot: VsBotDto = VsBotDto(),
)

@Serializable
data class ByModeDto(
    val local: Int = 0,
    @SerialName("vs_bot") val vsBot: Int = 0,
)

@Serializable
data class VsBotDto(val wins: Int = 0, val losses: Int = 0, val draws: Int = 0)
