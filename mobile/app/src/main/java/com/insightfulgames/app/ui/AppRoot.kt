package com.insightfulgames.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.insightfulgames.app.InsightfulApp
import com.insightfulgames.app.data.model.Session
import com.insightfulgames.app.ui.login.LoginScreen
import com.insightfulgames.app.ui.profile.ProfileScreen
import kotlinx.coroutines.flow.map

private sealed interface SessionState {
    data object Loading : SessionState
    data object LoggedOut : SessionState
    data class LoggedIn(val session: Session) : SessionState
}

/**
 * Raíz de la app: la sesión guardada decide la pantalla.
 * Login correcto => se guarda sesión => aparece el perfil.
 * Logout o 401 => se borra la sesión => vuelve el login.
 * Con más pantallas, aquí es donde entra Navigation Compose.
 */
@Composable
fun AppRoot() {
    val app = LocalContext.current.applicationContext as InsightfulApp
    val sessionFlow = remember {
        app.container.authRepository.session.map { session ->
            if (session == null) SessionState.LoggedOut else SessionState.LoggedIn(session)
        }
    }
    val state by sessionFlow.collectAsStateWithLifecycle(initialValue = SessionState.Loading)

    when (val current = state) {
        SessionState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        SessionState.LoggedOut -> LoginScreen()
        is SessionState.LoggedIn -> ProfileScreen(session = current.session)
    }
}
