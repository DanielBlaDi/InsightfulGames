package com.insightfulgames.app

import android.app.Application
import android.content.Context
import com.insightfulgames.app.data.local.SessionStore
import com.insightfulgames.app.data.remote.ApiClient
import com.insightfulgames.app.data.repository.AuthRepository
import com.insightfulgames.app.data.repository.StatsRepository
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
        sessionStore = sessionStore,
        // El gateway dijo 401 en una ruta protegida: se borra la sesión y la UI vuelve al login.
        onUnauthorized = { appScope.launch { sessionStore.clear() } },
    )

    val authRepository = AuthRepository(api, sessionStore)
    val statsRepository = StatsRepository(api)
}
