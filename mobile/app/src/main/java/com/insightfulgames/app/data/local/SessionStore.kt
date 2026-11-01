package com.insightfulgames.app.data.local

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.insightfulgames.app.data.model.Session
import com.insightfulgames.app.data.model.UserDto
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.sessionDataStore by preferencesDataStore(name = "session")

/**
 * Guarda el token y el usuario en el almacenamiento privado de la app (DataStore).
 * TODO: cifrar el token con una clave del Android Keystore antes de publicar.
 */
class SessionStore(context: Context) {
    private val store = context.applicationContext.sessionDataStore

    /** Sesión vigente, o null si no hay una o el token ya venció. */
    val session: Flow<Session?> = store.data.map { prefs ->
        val token = prefs[TOKEN]
        val userId = prefs[USER_ID]
        val username = prefs[USERNAME]
        val expiresAt = prefs[EXPIRES_AT]
        if (token != null && userId != null && username != null &&
            expiresAt != null && expiresAt > System.currentTimeMillis()
        ) {
            Session(token, userId, username)
        } else {
            null
        }
    }

    suspend fun save(token: String, user: UserDto, expiresInSeconds: Long) {
        store.edit { prefs ->
            prefs[TOKEN] = token
            prefs[USER_ID] = user.userId
            prefs[USERNAME] = user.username
            prefs[EXPIRES_AT] = System.currentTimeMillis() + expiresInSeconds * 1000
        }
    }

    suspend fun clear() {
        store.edit { it.clear() }
    }

    private companion object {
        val TOKEN = stringPreferencesKey("access_token")
        val USER_ID = stringPreferencesKey("user_id")
        val USERNAME = stringPreferencesKey("username")
        val EXPIRES_AT = longPreferencesKey("expires_at_ms")
    }
}
