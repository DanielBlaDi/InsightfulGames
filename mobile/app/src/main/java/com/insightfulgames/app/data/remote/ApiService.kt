package com.insightfulgames.app.data.remote

import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.model.LoginRequest
import com.insightfulgames.app.data.model.LoginResponse
import com.insightfulgames.app.data.model.StatsDto
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

/** Rutas del API Gateway (sin el prefijo /api, que solo existe en el nginx del frontend web). */
interface ApiService {
    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @GET("games")
    suspend fun games(): List<GameSummaryDto>

    /** Endpoint propuesto: mientras no exista, el gateway responde 404 y se calcula desde /games. */
    @GET("users/me/stats")
    suspend fun stats(): StatsDto
}
