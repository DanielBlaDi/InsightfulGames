package com.insightfulgames.app.ui.detail

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.ui.GameLabels
import com.insightfulgames.app.ui.LoadState
import com.insightfulgames.app.ui.components.ErrorBox
import com.insightfulgames.app.ui.components.FenBoard
import com.insightfulgames.app.ui.components.LoadingBox
import com.insightfulgames.app.ui.components.SectionCard
import com.insightfulgames.app.ui.components.outcomeColor
import com.insightfulgames.app.ui.container
import com.insightfulgames.app.ui.formatDateTime

/** Detalle de solo lectura. [kind] e [id] salen de la lista: GAME (local, vs_bot) o MATCH (multiplayer). */
@Composable
fun DetailScreen(
    kind: DetailKind,
    id: String,
    myUserId: String,
    modifier: Modifier = Modifier,
    viewModel: DetailViewModel = viewModel(
        key = "detail-${kind.name}-$id",
        factory = viewModelFactory {
            initializer { DetailViewModel(kind, id, container().gameRepository) }
        },
    ),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()

    when (val state = ui) {
        LoadState.Loading -> LoadingBox(modifier)
        is LoadState.Error -> ErrorBox(state.message, viewModel::load, modifier)
        is LoadState.Success -> DetailContent(state.data, myUserId, modifier)
    }
}

@Composable
private fun DetailContent(game: GameStateDto, myUserId: String, modifier: Modifier = Modifier) {
    val outcome = GameLabels.outcome(game)

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        SectionCard(GameLabels.modeLabel(game.mode)) {
            Text(
                GameLabels.outcomeLabel(outcome),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = outcomeColor(outcome),
            )
            GameLabels.endReasonLabel(game.endReason)?.let {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            InfoRow("Reloj", GameLabels.timeControlLabel(game))
            InfoRow("Visibilidad", GameLabels.visibilityLabel(game.visibility))
            InfoRow("Creada", formatDateTime(game.createdAt))
            if (game.finishedAt != null) InfoRow("Terminada", formatDateTime(game.finishedAt))
        }

        SectionCard("Jugadores") {
            InfoRow("Blancas", GameLabels.playerLabel(game, "white", myUserId))
            InfoRow("Negras", GameLabels.playerLabel(game, "black", myUserId))
        }

        FenBoard(game.fen)

        SectionCard("Jugadas") {
            if (game.moves.isEmpty()) {
                Text("Sin jugadas todavía.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                Text(GameLabels.movesText(game.moves), style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontWeight = FontWeight.Medium)
    }
}
