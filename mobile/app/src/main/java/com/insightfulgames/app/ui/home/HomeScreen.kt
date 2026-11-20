package com.insightfulgames.app.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.model.HomeDto
import com.insightfulgames.app.ui.AppViewModelProvider
import com.insightfulgames.app.ui.LoadState
import com.insightfulgames.app.ui.components.EMPTY_HISTORY_TEXT
import com.insightfulgames.app.ui.components.EmptyBox
import com.insightfulgames.app.ui.components.ErrorBox
import com.insightfulgames.app.ui.components.GameRow
import com.insightfulgames.app.ui.components.LoadingBox
import com.insightfulgames.app.ui.components.ScreenTitle
import com.insightfulgames.app.ui.components.SectionCard
import com.insightfulgames.app.ui.components.StatsSummary
import com.insightfulgames.app.ui.components.UnavailableCard
import com.insightfulgames.app.ui.formatDate

@Composable
fun HomeScreen(
    onOpenGame: (GameSummaryDto) -> Unit,
    onOpenHistory: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: HomeViewModel = viewModel(factory = AppViewModelProvider.Factory),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()

    when (val load = ui.load) {
        LoadState.Loading -> LoadingBox(modifier)
        is LoadState.Error -> ErrorBox(load.message, viewModel::refresh, modifier)
        is LoadState.Success -> HomeContent(
            data = load.data,
            refreshing = ui.refreshing,
            onRetry = viewModel::refresh,
            onOpenGame = onOpenGame,
            onOpenHistory = onOpenHistory,
            modifier = modifier,
        )
    }
}

@Composable
private fun HomeContent(
    data: HomeDto,
    refreshing: Boolean,
    onRetry: () -> Unit,
    onOpenGame: (GameSummaryDto) -> Unit,
    onOpenHistory: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenTitle(data.profile?.let { "Hola, ${it.username}" } ?: "Inicio")

        // Cada sección es independiente: si una falla, el resto se muestra normal.
        val profile = data.profile
        if (profile == null || "profile" in data.unavailable) {
            UnavailableCard("Perfil", onRetry, enabled = !refreshing)
        } else {
            SectionCard("Perfil") {
                Text(profile.username, style = MaterialTheme.typography.titleLarge)
                Text(
                    "Miembro desde ${formatDate(profile.createdAt)}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        val stats = data.stats
        if (stats == null || "stats" in data.unavailable) {
            UnavailableCard("Estadísticas", onRetry, enabled = !refreshing)
        } else {
            SectionCard("Estadísticas online") { StatsSummary(stats) }
        }

        val recent = data.recentGames
        if (recent == null || "recentGames" in data.unavailable) {
            UnavailableCard("Últimas partidas", onRetry, enabled = !refreshing)
        } else {
            SectionCard("Últimas partidas") {
                if (recent.isEmpty()) {
                    EmptyBox(EMPTY_HISTORY_TEXT)
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        recent.forEach { game -> GameRow(game, onClick = { onOpenGame(game) }) }
                    }
                    TextButton(onClick = onOpenHistory) { Text("Ver todo el historial") }
                }
            }
        }
    }
}
