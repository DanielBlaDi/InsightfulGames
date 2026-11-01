package com.insightfulgames.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.insightfulgames.app.InsightfulApp
import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.model.Session
import com.insightfulgames.app.data.model.SessionState
import com.insightfulgames.app.ui.auth.AuthScreen
import com.insightfulgames.app.ui.detail.DetailScreen
import com.insightfulgames.app.ui.history.HistoryScreen
import com.insightfulgames.app.ui.home.HomeScreen
import com.insightfulgames.app.ui.profile.ProfileScreen
import com.insightfulgames.app.ui.stats.StatsScreen

private const val ROUTE_HOME = "home"
private const val ROUTE_PROFILE = "profile"
private const val ROUTE_STATS = "stats"
private const val ROUTE_HISTORY = "history"
private const val ROUTE_DETAIL = "detail/{kind}/{id}"

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    Tab(ROUTE_HOME, "Inicio", Icons.Filled.Home),
    Tab(ROUTE_PROFILE, "Perfil", Icons.Filled.Person),
    Tab(ROUTE_STATS, "Estadísticas", Icons.Filled.Star),
    Tab(ROUTE_HISTORY, "Historial", Icons.AutoMirrored.Filled.List),
)

/**
 * Raíz de la app: la sesión guardada decide la pantalla.
 * Login correcto => se guarda la sesión => aparece la app.
 * Logout o 401 => se borra la sesión => vuelve el login (con aviso si fue 401).
 */
@Composable
fun AppRoot() {
    val app = LocalContext.current.applicationContext as InsightfulApp
    val state by app.container.sessionStore.state.collectAsStateWithLifecycle()

    when (val current = state) {
        SessionState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        SessionState.LoggedOut -> AuthScreen()
        is SessionState.LoggedIn -> MainScaffold(current.session)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainScaffold(session: Session) {
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    val isTab = tabs.any { it.route == route }

    Scaffold(
        topBar = {
            if (route == ROUTE_DETAIL) {
                TopAppBar(
                    title = { Text("Detalle de partida") },
                    navigationIcon = {
                        IconButton(onClick = { nav.popBackStack() }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Volver")
                        }
                    },
                )
            }
        },
        bottomBar = {
            if (isTab) {
                NavigationBar {
                    tabs.forEach { tab ->
                        NavigationBarItem(
                            selected = backStack?.destination?.hierarchy?.any { it.route == tab.route } == true,
                            onClick = { nav.navigateToTab(tab.route) },
                            icon = { Icon(tab.icon, contentDescription = null) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(nav, startDestination = ROUTE_HOME, modifier = Modifier.padding(padding)) {
            composable(ROUTE_HOME) {
                HomeScreen(
                    onOpenGame = { nav.openDetail(it) },
                    onOpenHistory = { nav.navigateToTab(ROUTE_HISTORY) },
                )
            }
            composable(ROUTE_PROFILE) { ProfileScreen() }
            composable(ROUTE_STATS) { StatsScreen() }
            composable(ROUTE_HISTORY) { HistoryScreen(onOpenGame = { nav.openDetail(it) }) }
            composable(
                ROUTE_DETAIL,
                arguments = listOf(
                    navArgument("kind") { type = NavType.StringType },
                    navArgument("id") { type = NavType.StringType },
                ),
            ) { entry ->
                val kind = entry.arguments?.getString("kind")
                    ?.let { k -> DetailKind.entries.firstOrNull { it.name.equals(k, ignoreCase = true) } }
                val id = entry.arguments?.getString("id")
                if (kind != null && id != null) {
                    DetailScreen(kind = kind, id = id, myUserId = session.userId)
                }
            }
        }
    }
}

private fun NavController.navigateToTab(route: String) {
    navigate(route) {
        popUpTo(graph.findStartDestination().id) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/** local y vs_bot -> /games/{gameId}; multiplayer -> /matches/{matchId} (ver GameLabels.detailTarget). */
private fun NavController.openDetail(game: GameSummaryDto) {
    val target = GameLabels.detailTarget(game)
    navigate("detail/${target.kind.name.lowercase()}/${target.id}")
}
