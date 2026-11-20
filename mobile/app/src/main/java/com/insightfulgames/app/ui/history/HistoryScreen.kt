package com.insightfulgames.app.ui.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
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
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.ui.AppViewModelProvider
import com.insightfulgames.app.ui.components.EMPTY_HISTORY_TEXT
import com.insightfulgames.app.ui.components.EmptyBox
import com.insightfulgames.app.ui.components.ErrorBox
import com.insightfulgames.app.ui.components.GameRow
import com.insightfulgames.app.ui.components.LoadingBox
import com.insightfulgames.app.ui.components.ScreenTitle

@Composable
fun HistoryScreen(
    onOpenGame: (GameSummaryDto) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: HistoryViewModel = viewModel(factory = AppViewModelProvider.Factory),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()

    when {
        ui.initialLoading -> LoadingBox(modifier)
        ui.error != null && ui.items.isEmpty() -> ErrorBox(ui.error.orEmpty(), viewModel::loadFirst, modifier)
        else -> LazyColumn(
            modifier = modifier.fillMaxSize(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item { ScreenTitle("Historial", Modifier.padding(bottom = 8.dp)) }

            if (ui.items.isEmpty()) {
                item { EmptyBox(EMPTY_HISTORY_TEXT) }
            } else {
                items(ui.items, key = { it.gameId }) { game ->
                    GameRow(game, onClick = { onOpenGame(game) })
                }
            }

            item {
                Column(
                    Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    // Error al cargar más: las partidas ya cargadas se quedan en pantalla.
                    ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    when {
                        ui.loadingMore -> Box(contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                        ui.nextCursor != null && ui.error != null ->
                            Button(onClick = viewModel::loadMore) { Text("Reintentar") }
                        ui.nextCursor != null ->
                            OutlinedButton(onClick = viewModel::loadMore) { Text("Cargar más") }
                    }
                }
            }
        }
    }
}
