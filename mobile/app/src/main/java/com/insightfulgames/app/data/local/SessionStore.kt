package com.insightfulgames.app.data.local

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.insightfulgames.app.data.model.Session
import com.insightfulgames.app.data.model.SessionState
import com.insightfulgames.app.data.model.UserDto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

/**
 * Guarda el token y el usuario cifrados con una clave del Android Keystore
 * (EncryptedSharedPreferences). Nunca en texto plano (sección 16 del contrato).
 *
 * - Sin refresh token: a los 3600 s el token vence y se vuelve al login.
 * - [load] debe llamarse una vez al arrancar; hasta entonces el estado es Loading.
 */
class SessionStore(context: Context) {
    private val appContext = context.applicationContext

    private val prefs: SharedPreferences by lazy { createPrefs() }

    private val _state = MutableStateFlow<SessionState>(SessionState.Loading)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    /** true si la sesión se cerró porque el gateway respondió 401 (sesión expirada). */
    private val _expired = MutableStateFlow(false)
    val expired: StateFlow<Boolean> = _expired.asStateFlow()

    /** Token vigente, leído por el interceptor de red desde hilos de OkHttp. */
    @Volatile
    var token: String? = null
        private set

    /** Lee la sesión guardada. Descarta un token ya vencido. */
    suspend fun load() = withContext(Dispatchers.IO) {
        val t = prefs.getString(TOKEN, null)
        val userId = prefs.getString(USER_ID, null)
        val username = prefs.getString(USERNAME, null)
        val expiresAt = prefs.getLong(EXPIRES_AT, 0L)

        if (t != null && userId != null && username != null && expiresAt > System.currentTimeMillis()) {
            token = t
            _state.value = SessionState.LoggedIn(Session(t, userId, username))
        } else {
            prefs.edit().clear().apply()
            token = null
            _state.value = SessionState.LoggedOut
        }
    }

    suspend fun save(accessToken: String, user: UserDto, expiresInSeconds: Long) =
        withContext(Dispatchers.IO) {
            prefs.edit()
                .putString(TOKEN, accessToken)
                .putString(USER_ID, user.userId)
                .putString(USERNAME, user.username)
                .putLong(EXPIRES_AT, System.currentTimeMillis() + expiresInSeconds * 1000)
                .apply()
            token = accessToken
            _expired.value = false
            _state.value = SessionState.LoggedIn(Session(accessToken, user.userId, user.username))
        }

    /** Cerrar sesión: solo borra el token local (la app no usa /auth/logout). */
    suspend fun clear() = withContext(Dispatchers.IO) {
        wipe()
        _expired.value = false
    }

    /**
     * El gateway respondió 401 con [tokenUsed]. Se borra la sesión y se marca como expirada.
     * Si mientras tanto hubo un login nuevo (otro token), se ignora el 401 viejo.
     */
    suspend fun expire(tokenUsed: String?) = withContext(Dispatchers.IO) {
        if (tokenUsed != null && tokenUsed != token) return@withContext
        wipe()
        _expired.value = true
    }

    private fun wipe() {
        prefs.edit().clear().apply()
        token = null
        _state.value = SessionState.LoggedOut
    }

    private fun createPrefs(): SharedPreferences {
        fun build(): SharedPreferences {
            val masterKey = MasterKey.Builder(appContext)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            return EncryptedSharedPreferences.create(
                appContext,
                FILE,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        }
        return try {
            build()
        } catch (e: Exception) {
            // Keystore o archivo corrompido (p. ej. tras restaurar el teléfono): se parte de cero.
            appContext.deleteSharedPreferences(FILE)
            build()
        }
    }

    private companion object {
        const val FILE = "session_secure"
        const val TOKEN = "access_token"
        const val USER_ID = "user_id"
        const val USERNAME = "username"
        const val EXPIRES_AT = "expires_at_ms"
    }
}
