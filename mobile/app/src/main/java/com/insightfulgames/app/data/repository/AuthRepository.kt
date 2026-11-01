package com.insightfulgames.app.data.repository

import com.insightfulgames.app.data.local.SessionStore
import com.insightfulgames.app.data.model.LoginRequest
import com.insightfulgames.app.data.model.Session
import com.insightfulgames.app.data.remote.ApiService
import com.insightfulgames.app.data.remote.apiCall
import kotlinx.coroutines.flow.Flow

class AuthRepository(
    private val api: ApiService,
    private val sessionStore: SessionStore,
) {
    val session: Flow<Session?> = sessionStore.session

    suspend fun login(username: String, password: String): Result<Unit> =
        apiCall { api.login(LoginRequest(username.trim(), password)) }
            .mapCatching { sessionStore.save(it.accessToken, it.user, it.expiresIn) }

    suspend fun logout() = sessionStore.clear()
}
