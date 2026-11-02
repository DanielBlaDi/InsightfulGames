package com.insightfulgames.app.data.repository

import com.insightfulgames.app.data.local.SessionStore
import com.insightfulgames.app.data.model.LoginRequest
import com.insightfulgames.app.data.model.RegisterRequest
import com.insightfulgames.app.data.remote.ApiService
import com.insightfulgames.app.data.remote.apiCall
import kotlinx.coroutines.flow.StateFlow

class AuthRepository(
    private val api: ApiService,
    private val sessionStore: SessionStore,
) {
    val sessionExpired: StateFlow<Boolean> = sessionStore.expired

    suspend fun login(username: String, password: String): Result<Unit> =
        apiCall { api.login(LoginRequest(username.trim(), password)) }
            .mapCatching { sessionStore.save(it.accessToken, it.user, it.expiresIn) }

    /** Registra y, si sale bien, inicia sesión con las mismas credenciales. */
    suspend fun register(username: String, password: String): Result<Unit> {
        val registered = apiCall { api.register(RegisterRequest(username.trim(), password)) }
        if (registered.isFailure) return Result.failure(registered.exceptionOrNull()!!)
        return login(username, password)
    }

    /** La app no usa /auth/logout (no hay cookie): solo borra el token del teléfono. */
    suspend fun logout() = sessionStore.clear()
}
