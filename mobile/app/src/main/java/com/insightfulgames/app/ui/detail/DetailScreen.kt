package com.insightfulgames.app.ui.detail

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.model.Outcome
import com.insightfulgames.app.ui.GameLabels
import com.insightfulgames.app.ui.LoadState
import com.insightfulgames.app.ui.MoveCell
import com.insightfulgames.app.ui.MoveRow
import com.insightfulgames.app.ui.Replay
import com.insightfulgames.app.ui.buildReplay
import com.insightfulgames.app.ui.components.ErrorBox
import com.insightfulgames.app.ui.components.FenBoard
import com.insightfulgames.app.ui.components.LoadingBox
import com.insightfulgames.app.ui.components.SectionCard
import com.insightfulgames.app.ui.components.outcomeColor
import com.insightfulgames.app.ui.container
import com.insightfulgames.app.ui.formatDateTime
import com.insightfulgames.app.ui.moveRowIndex
import com.insightfulgames.app.ui.moveRows
import com.insightfulgames.app.ui.uciSquares

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
    // Cada jugada trae fenAfter (contrato, sección 19): con eso se navega sin recalcular nada.
    val replay = remember(game) { buildReplay(game.initialFen, game.moves) }
    if (replay != null) {
        ReplayDetailContent(game, replay, myUserId, modifier)
    } else {
        // Sin fenAfter no se puede navegar: se muestra la posición final y las jugadas en texto.
        StaticDetailContent(game, myUserId, modifier)
    }
}

/**
 * Tablero arriba con flechas (inicio, anterior, siguiente, final) y, debajo, la lista de jugadas
 * (tocar una salta a esa posición) y los datos de la partida. Arranca en la posición inicial.
 */
@Composable
private fun ReplayDetailContent(
    game: GameStateDto,
    replay: Replay,
    myUserId: String,
    modifier: Modifier = Modifier,
) {
    val outcome = GameLabels.outcome(game, myUserId)
    // rememberSaveable: al girar la pantalla se queda en la misma jugada.
    var requestedPly by rememberSaveable(game.gameId) { mutableStateOf(0) }
    val ply = replay.clamp(requestedPly)
    val rows = remember(replay) { moveRows(replay.moves) }
    val listState = rememberLazyListState()

    // Mantiene visible en la lista la jugada que se está mostrando en el tablero.
    LaunchedEffect(ply) {
        if (ply == 0) {
            listState.animateScrollToItem(0)
        } else {
            val item = moveRowIndex(rows, ply) + 1 // +1: el primer elemento de la lista es el título
            val visible = listState.layoutInfo.visibleItemsInfo.any { it.index == item }
            if (item >= 1 && !visible) listState.animateScrollToItem((item - 1).coerceAtLeast(0))
        }
    }

    BoxWithConstraints(modifier.fillMaxSize()) {
        // El tablero ocupa el ancho, pero nunca más de la mitad de la altura (así cabe en horizontal).
        val boardSize = maxOf(minOf(maxWidth - 32.dp, maxHeight * 0.55f, 480.dp), 120.dp)

        Column(Modifier.fillMaxSize()) {
            Column(
                Modifier.fillMaxWidth().padding(top = 12.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Column(Modifier.width(boardSize), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutcomeHeader(game, outcome)
                    FenBoard(
                        fen = replay.fenAt(ply),
                        lastMove = replay.moveAt(ply)?.let { uciSquares(it.uci) },
                    )
                    Text(
                        GameLabels.replayCaption(ply, replay.lastPly, replay.moveAt(ply)),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    ReplayControls(ply = ply, last = replay.lastPly, onChange = { requestedPly = it })
                }
            }

            LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                item {
                    Text(
                        "Jugadas",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(bottom = 6.dp),
                    )
                }
                if (rows.isEmpty()) {
                    item { Text("Sin jugadas todavía.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
                } else {
                    items(rows) { row -> MoveRowView(row, ply) { requestedPly = it } }
                }
                item {
                    Column(
                        Modifier.padding(top = 16.dp),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        GameInfoCards(game, myUserId, outcome, showOutcome = false)
                    }
                }
            }
        }
    }
}

@Composable
private fun OutcomeHeader(game: GameStateDto, outcome: Outcome) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            GameLabels.outcomeLabel(outcome),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = outcomeColor(outcome),
        )
        GameLabels.endReasonLabel(game.endReason)?.let {
            Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ReplayControls(ply: Int, last: Int, onChange: (Int) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        ReplayButton("«", "Ir al inicio", enabled = ply > 0, modifier = Modifier.weight(1f)) { onChange(0) }
        ReplayButton("‹", "Jugada anterior", enabled = ply > 0, modifier = Modifier.weight(1f)) { onChange(ply - 1) }
        ReplayButton("›", "Jugada siguiente", enabled = ply < last, modifier = Modifier.weight(1f)) { onChange(ply + 1) }
        ReplayButton("»", "Ir al final", enabled = ply < last, modifier = Modifier.weight(1f)) { onChange(last) }
    }
}

@Composable
private fun ReplayButton(
    glyph: String,
    description: String,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    FilledTonalButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(48.dp).semantics { contentDescription = description },
        contentPadding = PaddingValues(0.dp),
    ) {
        Text(glyph, fontSize = 28.sp, fontWeight = FontWeight.Bold)
    }
}

/** "12. Nf3 Nc6": cada jugada es tocable; la que se ve en el tablero queda resaltada. */
@Composable
private fun MoveRowView(row: MoveRow, currentPly: Int, onSelect: (Int) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            "${row.number}.",
            modifier = Modifier.width(36.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        MoveCellView(row.white, currentPly, onSelect, Modifier.weight(1f))
        MoveCellView(row.black, currentPly, onSelect, Modifier.weight(1f))
    }
}

@Composable
private fun MoveCellView(cell: MoveCell?, currentPly: Int, onSelect: (Int) -> Unit, modifier: Modifier = Modifier) {
    if (cell == null) {
        Spacer(modifier)
        return
    }
    val selected = cell.position == currentPly
    Box(
        modifier
            .clip(RoundedCornerShape(6.dp))
            .background(if (selected) MaterialTheme.colorScheme.primaryContainer else Color.Transparent)
            .clickable { onSelect(cell.position) }
            .padding(horizontal = 10.dp, vertical = 8.dp),
    ) {
        Text(
            cell.san,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
            color = if (selected) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurface,
        )
    }
}

/** Respaldo: posición final y jugadas en texto (como antes). Solo si alguna jugada no trae fenAfter. */
@Composable
private fun StaticDetailContent(game: GameStateDto, myUserId: String, modifier: Modifier = Modifier) {
    val outcome = GameLabels.outcome(game, myUserId)

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        GameInfoCards(game, myUserId, outcome, showOutcome = true)

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

/** Tarjetas de modo/reloj/fechas y de jugadores. [showOutcome] = false cuando el resultado ya se muestra sobre el tablero. */
@Composable
private fun GameInfoCards(game: GameStateDto, myUserId: String, outcome: Outcome, showOutcome: Boolean) {
    SectionCard(GameLabels.modeLabel(game.mode)) {
        if (showOutcome) {
            Text(
                GameLabels.outcomeLabel(outcome),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = outcomeColor(outcome),
            )
            GameLabels.endReasonLabel(game.endReason)?.let {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
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
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontWeight = FontWeight.Medium)
    }
}
