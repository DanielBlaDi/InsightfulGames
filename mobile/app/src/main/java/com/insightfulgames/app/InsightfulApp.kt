package com.insightfulgames.app

import android.app.Application
import android.content.Context
import com.insightfulgames.app.data.local.SessionStore
import com.insightfulgames.app.data.remote.ApiClient
import com.insightfulgames.app.data.repository.AuthRepository
import com.insightfulgames.app.data.repository.GameRepository
import com.insightfulgames.app.data.repository.ProfileRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class InsightfulApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}

/** Inyección de dependencias manual: suficiente para este tamaño. */
class AppContainer(context: Context) {
    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val sessionStore = SessionStore(context)

    private val api = ApiClient.create(
        baseUrl = BuildConfig.BASE_URL,
        tokenProvider = { sessionStore.token },
        // El gateway respondió 401 en una ruta protegida: se borra la sesión y la UI vuelve al login.
        onUnauthorized = { tokenUsed -> appScope.launch { sessionStore.expire(tokenUsed) } },
    )

    val authRepository = AuthRepository(api, sessionStore)
    val profileRepository = ProfileRepository(api)
    val gameRepository = GameRepository(api)

    init {
        // Lee la sesión cifrada fuera del hilo principal. Hasta entonces el estado es Loading.
        appScope.launch { sessionStore.load() }
    }
}
