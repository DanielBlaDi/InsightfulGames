package com.insightfulgames.app.ui.play

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.ui.GameLabels
import com.insightfulgames.app.ui.components.ErrorBox
import com.insightfulgames.app.ui.components.FenBoard
import com.insightfulgames.app.ui.components.LoadingBox
import com.insightfulgames.app.ui.components.ScreenTitle
import com.insightfulgames.app.ui.components.SectionCard
import com.insightfulgames.app.ui.container
import com.insightfulgames.app.ui.pieceGlyph
import com.insightfulgames.app.ui.uciSquares
import kotlinx.coroutines.delay
import java.time.Instant

private const val LOCAL_MINUTES = 10 // único control de tiempo que acepta el backend

/** Pestaña Jugar: configura y crea una partida local. [onCreated] navega a la partida. */
@Composable
fun NewGameScreen(
    onCreated: (String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: NewGameViewModel = viewModel(
        factory = viewModelFactory { initializer { NewGameViewModel(container().gameRepository) } },
    ),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()

    LaunchedEffect(ui.created) {
        ui.created?.let {
            viewModel.consumeCreated()
            onCreated(it)
        }
    }

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        ScreenTitle("Jugar")
        SectionCard("Partida local") {
            Text(
                "Dos jugadores en este teléfono: cada uno mueve en su turno. La partida queda en tu historial.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TimeOption("Sin reloj", selected = ui.minutes == null) { viewModel.setMinutes(null) }
            TimeOption("$LOCAL_MINUTES minutos por bando", selected = ui.minutes == LOCAL_MINUTES) {
                viewModel.setMinutes(LOCAL_MINUTES)
            }
            ui.error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            Button(onClick = viewModel::create, enabled = !ui.creating, modifier = Modifier.fillMaxWidth()) {
                if (ui.creating) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                } else {
                    Text("Empezar partida")
                }
            }
        }
    }
}

@Composable
private fun TimeOption(label: String, selected: Boolean, onSelect: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().selectable(selected = selected, onClick = onSelect).padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null)
        Text(label, modifier = Modifier.padding(start = 8.dp))
    }
}

/** Partida local en vivo. [onNewGame] vuelve a la pestaña Jugar. */
@Composable
fun PlayScreen(
    gameId: String,
    onNewGame: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: PlayViewModel = viewModel(
        key = "play-$gameId",
        factory = viewModelFactory { initializer { PlayViewModel(gameId, container().gameRepository) } },
    ),
) {
    val ui by viewModel.ui.collectAsStateWithLifecycle()
    val game = ui.game

    when {
        game == null && ui.loadError != null -> ErrorBox(ui.loadError!!, viewModel::load, modifier)
        game == null -> LoadingBox(modifier)
        else -> PlayContent(game, ui, viewModel, onNewGame, modifier)
    }
}

@Composable
private fun PlayContent(
    game: GameStateDto,
    ui: PlayUi,
    viewModel: PlayViewModel,
    onNewGame: () -> Unit,
    modifier: Modifier,
) {
    val playing = game.status == "in_progress"
    var confirmResign by remember { mutableStateOf(false) }

    // Relojes: se recalculan cada 200 ms mientras corren. Al llegar a 0 se pide al backend el cierre.
    var now by remember { mutableStateOf(Instant.now()) }
    val running = playing && game.clocks?.deadline != null
    LaunchedEffect(running, game.version) {
        while (running) {
            now = Instant.now()
            val left = game.turn?.let { MoveInput.remainingMs(game.clocks, it, game.turn, game.status, now) }
            if (left == 0L) viewModel.onClockExpired()
            delay(200)
        }
    }

    val topColor = if (ui.flipped) "white" else "black"
    val bottomColor = if (ui.flipped) "black" else "white"
    val targets = remember(game.version, ui.selected) {
        ui.selected?.let { MoveInput.targets(game.legalMoves, it) } ?: emptySet()
    }

    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(Modifier.widthIn(max = 480.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            StatusLine(game)
            PlayerBar(game, topColor, now)
            FenBoard(
                fen = game.fen,
                lastMove = game.moves.lastOrNull()?.let { uciSquares(it.uci) },
                selected = ui.selected,
                targets = targets,
                flipped = ui.flipped,
                onSquareClick = if (playing && !ui.sending) viewModel::onSquare else null,
            )
            PlayerBar(game, bottomColor, now)

            ui.notice?.let {
                Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = viewModel::flip, modifier = Modifier.weight(1f)) { Text("Girar tablero") }
                if (playing) {
                    OutlinedButton(
                        onClick = { confirmResign = true },
                        enabled = !ui.sending,
                        modifier = Modifier.weight(1f),
                    ) { Text("Rendirse") }
                } else {
                    Button(onClick = onNewGame, modifier = Modifier.weight(1f)) { Text("Nueva partida") }
                }
            }

            SectionCard("Jugadas") {
                val text = GameLabels.movesText(game.moves)
                Text(
                    text.ifEmpty { "Sin jugadas todavía." },
                    color = if (text.isEmpty()) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }

    if (confirmResign) {
        val side = game.turn?.let { GameLabels.colorLabel(it).lowercase() } ?: ""
        AlertDialog(
            onDismissRequest = { confirmResign = false },
            title = { Text("¿Rendirse?") },
            text = { Text("Se rinden las $side, que tienen el turno. La partida termina.") },
            confirmButton = {
                TextButton(onClick = { confirmResign = false; viewModel.resign() }) { Text("Rendirse") }
            },
            dismissButton = { TextButton(onClick = { confirmResign = false }) { Text("Cancelar") } },
        )
    }

    ui.pendingPromotion?.let {
        val white = game.turn == "white"
        AlertDialog(
            onDismissRequest = viewModel::cancelPromotion,
            title = { Text("Coronar") },
            text = {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (piece in listOf('q', 'r', 'b', 'n')) {
                        OutlinedButton(onClick = { viewModel.promote(piece) }, modifier = Modifier.weight(1f)) {
                            Text(pieceGlyph(if (white) piece.uppercaseChar() else piece), fontSize = 24.sp)
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = viewModel::cancelPromotion) { Text("Cancelar") } },
        )
    }

    if (ui.justFinished) {
        AlertDialog(
            onDismissRequest = viewModel::dismissResult,
            title = { Text(resultTitle(game)) },
            text = { GameLabels.endReasonLabel(game.endReason)?.let { Text(it) } },
            confirmButton = {
                TextButton(onClick = { viewModel.dismissResult(); onNewGame() }) { Text("Nueva partida") }
            },
            dismissButton = { TextButton(onClick = viewModel::dismissResult) { Text("Ver tablero") } },
        )
    }
}

private fun resultTitle(game: GameStateDto): String =
    GameLabels.outcomeLabel(GameLabels.outcome(game.status, game.result, game.endReason, color = null))

@Composable
private fun StatusLine(game: GameStateDto) {
    val text = if (game.status == "in_progress") {
        if (game.turn == "black") "Juegan negras" else "Juegan blancas"
    } else {
        listOfNotNull(resultTitle(game), GameLabels.endReasonLabel(game.endReason)).joinToString(" · ")
    }
    Text(
        text,
        style = MaterialTheme.typography.titleLarge,
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.primary,
    )
}

/** Nombre del color y, si hay reloj, su tiempo. Resaltado cuando le toca mover. */
@Composable
private fun PlayerBar(game: GameStateDto, color: String, now: Instant) {
    val active = game.status == "in_progress" && game.turn == color
    val left = MoveInput.remainingMs(game.clocks, color, game.turn, game.status, now)
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            GameLabels.colorLabel(color),
            fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
            color = if (active) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (left != null) {
            Surface(
                color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                contentColor = if (active) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                shape = MaterialTheme.shapes.small,
            ) {
                Text(
                    MoveInput.clockText(left),
                    fontFamily = FontFamily.Monospace,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                )
            }
        }
    }
}
