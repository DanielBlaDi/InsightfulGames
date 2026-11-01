package com.insightfulgames.app.ui.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.insightfulgames.app.data.model.BotRecord
import com.insightfulgames.app.data.model.Outcome
import com.insightfulgames.app.data.model.ProfileData
import com.insightfulgames.app.data.model.ProfileStats
import com.insightfulgames.app.data.model.RecentGame
import com.insightfulgames.app.data.model.Session
import com.insightfulgames.app.ui.AppViewModelProvider
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(
    session: Session,
    // key = userId: si se cierra sesión y entra otro usuario, no se reutiliza el ViewModel anterior.
    viewModel: ProfileViewModel = viewModel(key = session.userId, factory = AppViewModelProvider.Factory),
) {
    val state by viewModel.ui.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Mi perfil", fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold) },
                actions = {
                    TextButton(onClick = viewModel::refresh) { Text("Actualizar") }
                    TextButton(onClick = viewModel::logout) { Text("Salir") }
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val s = state) {
                ProfileUiState.Loading -> CircularProgressIndicator(Modifier.align(Alignment.Center))
                is ProfileUiState.Error -> Column(
                    Modifier.align(Alignment.Center).padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(s.message, color = MaterialTheme.colorScheme.error)
                    Button(onClick = viewModel::refresh) { Text("Reintentar") }
                }
                is ProfileUiState.Success -> ProfileContent(session.username, s.data)
            }
        }
    }
}

@Composable
private fun ProfileContent(username: String, data: ProfileData) {
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Text(
                text = username,
                style = MaterialTheme.typography.headlineMedium,
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        item { StatsGrid(data.stats) }
        item { BotRecordCard(data.stats.botRecord) }
        item {
            Text(
                "Partidas recientes",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
        if (data.recent.isEmpty()) {
            item {
                Text(
                    "Todavía no has jugado ninguna partida.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            items(data.recent, key = { it.gameId }) { GameRow(it) }
        }
    }
}

@Composable
private fun StatsGrid(stats: ProfileStats) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        StatCard("Partidas jugadas", stats.totalGames.toString(), Modifier.fillMaxWidth(), highlighted = true)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Terminadas", stats.finished.toString(), Modifier.weight(1f))
            StatCard("En curso", stats.inProgress.toString(), Modifier.weight(1f))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StatCard("Contra el bot", stats.botGames.toString(), Modifier.weight(1f))
            StatCard("Local", stats.localGames.toString(), Modifier.weight(1f))
        }
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier = Modifier, highlighted: Boolean = false) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = if (highlighted) MaterialTheme.colorScheme.primaryContainer
            else MaterialTheme.colorScheme.surfaceContainerLow,
            contentColor = if (highlighted) MaterialTheme.colorScheme.onPrimaryContainer
            else MaterialTheme.colorScheme.onSurface,
        ),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(value, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
private fun BotRecordCard(record: BotRecord?) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "Récord contra el bot",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            if (record == null) {
                Text(
                    "Aún no disponible: el backend debe exponer /users/me/stats o incluir playerColor en GET /games.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    RecordItem("Victorias", record.wins)
                    RecordItem("Derrotas", record.losses)
                    RecordItem("Tablas", record.draws)
                }
                if (record.played > 0) {
                    Text(
                        "Porcentaje de victorias: ${(record.winRate * 100).toInt()} %",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
    }
}

@Composable
private fun RecordItem(label: String, value: Int) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun GameRow(game: RecentGame) {
    val title = if (game.mode == "vs_bot") {
        game.botLevel?.let { "Contra el bot (nivel $it)" } ?: "Contra el bot"
    } else {
        "Local (2 jugadores)"
    }
    ListItem(
        headlineContent = { Text(title) },
        supportingContent = { Text(formatDate(game.createdAt)) },
        trailingContent = {
            Text(
                text = outcomeLabel(game.outcome),
                fontWeight = FontWeight.SemiBold,
                color = outcomeColor(game.outcome),
            )
        },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
    )
}

private fun outcomeLabel(outcome: Outcome) = when (outcome) {
    Outcome.WIN -> "Victoria"
    Outcome.LOSS -> "Derrota"
    Outcome.DRAW -> "Tablas"
    Outcome.IN_PROGRESS -> "En curso"
    Outcome.LOCAL_FINISHED, Outcome.UNKNOWN -> "Finalizada"
}

@Composable
private fun outcomeColor(outcome: Outcome): Color = when (outcome) {
    Outcome.WIN -> MaterialTheme.colorScheme.secondary
    Outcome.LOSS -> MaterialTheme.colorScheme.error
    Outcome.IN_PROGRESS -> MaterialTheme.colorScheme.primary
    else -> MaterialTheme.colorScheme.onSurfaceVariant
}

private fun formatDate(iso: String): String = try {
    DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
        .withZone(ZoneId.systemDefault())
        .format(Instant.parse(iso))
} catch (e: Exception) {
    iso
}
