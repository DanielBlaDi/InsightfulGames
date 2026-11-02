package com.insightfulgames.app.ui.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.insightfulgames.app.ui.AppViewModelProvider
import com.insightfulgames.app.ui.LoadState
import com.insightfulgames.app.ui.components.ScreenTitle
import com.insightfulgames.app.ui.components.SectionCard
import com.insightfulgames.app.ui.formatDate

/**
 * [sessionUsername] viene de la sesión guardada: si el servicio de perfil no responde, se sigue
 * mostrando quién es el usuario y el botón de cerrar sesión siempre está disponible.
 */
@Composable
fun ProfileScreen(
    sessionUsername: String,
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = viewModel(factory = AppViewModelProvider.Factory),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenTitle("Perfil")

        when (val state = ui) {
            LoadState.Loading -> Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            is LoadState.Error -> SectionCard("Cuenta") {
                Text(sessionUsername, style = MaterialTheme.typography.headlineSmall)
                Text(state.message, color = MaterialTheme.colorScheme.error)
                OutlinedButton(onClick = viewModel::load) { Text("Reintentar") }
            }
            is LoadState.Success -> SectionCard("Cuenta") {
                Text(state.data.username, style = MaterialTheme.typography.headlineSmall)
                Text(
                    "Miembro desde ${formatDate(state.data.createdAt)}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // Solo borra el token del teléfono; la app no usa /auth/logout.
        OutlinedButton(onClick = viewModel::logout, modifier = Modifier.fillMaxWidth()) {
            Text("Cerrar sesión")
        }
    }
}
