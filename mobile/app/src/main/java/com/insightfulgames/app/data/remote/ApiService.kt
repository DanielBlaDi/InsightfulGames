package com.insightfulgames.app.data.remote

import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.model.GamesPageDto
import com.insightfulgames.app.data.model.HomeDto
import com.insightfulgames.app.data.model.LoginRequest
import com.insightfulgames.app.data.model.LoginResponse
import com.insightfulgames.app.data.model.ProfileDto
import com.insightfulgames.app.data.model.RegisterRequest
import com.insightfulgames.app.data.model.RegisterResponse
import com.insightfulgames.app.data.model.StatsDto
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** Rutas del API Gateway móvil (sección 5). Sin prefijo /api. */
interface ApiService {
    @POST("auth/register")
    suspend fun register(@Body body: RegisterRequest): RegisterResponse

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @GET("home")
    suspend fun home(): HomeDto

    @GET("profile/me")
    suspend fun profile(): ProfileDto

    @GET("stats/me")
    suspend fun stats(): StatsDto

    /** 20 por página (máximo del contrato). [cursor] sale de nextCursor de la página anterior. */
    @GET("games")
    suspend fun games(
        @Query("limit") limit: Int = 20,
        @Query("cursor") cursor: String? = null,
    ): GamesPageDto

    /** Detalle de partidas local y vs_bot. */
    @GET("games/{id}")
    suspend fun game(@Path("id") gameId: String): GameStateDto

    /** Detalle de partidas multiplayer (id = matchId). */
    @GET("matches/{id}")
    suspend fun match(@Path("id") matchId: String): GameStateDto
}
