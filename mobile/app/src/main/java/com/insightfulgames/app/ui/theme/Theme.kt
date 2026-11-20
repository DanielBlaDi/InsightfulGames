package com.insightfulgames.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Paleta "Terracotta & Tallow" (Frontend/desing/.../terracotta_tallow/DESIGN.md).
private val TerracottaLight = lightColorScheme(
    primary = Color(0xFFA53605),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFC74E1F),
    onPrimaryContainer = Color(0xFFFFFBFF),
    inversePrimary = Color(0xFFFFB59C),
    secondary = Color(0xFF55624A),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFD9E8C8),
    onSecondaryContainer = Color(0xFF5B694F),
    tertiary = Color(0xFF7B5414),
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFF976D2B),
    onTertiaryContainer = Color(0xFFFFFBFF),
    background = Color(0xFFFFF8F6),
    onBackground = Color(0xFF1F1B1A),
    surface = Color(0xFFFFF8F6),
    onSurface = Color(0xFF1F1B1A),
    surfaceVariant = Color(0xFFEAE1DE),
    onSurfaceVariant = Color(0xFF58423A),
    inverseSurface = Color(0xFF342F2E),
    inverseOnSurface = Color(0xFFF8EFED),
    outline = Color(0xFF8C7169),
    outlineVariant = Color(0xFFE0C0B6),
    error = Color(0xFFBA1A1A),
    onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFFFDAD6),
    onErrorContainer = Color(0xFF93000A),
    surfaceContainerLowest = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFFBF2EF),
    surfaceContainer = Color(0xFFF5ECEA),
    surfaceContainerHigh = Color(0xFFEFE6E4),
    surfaceContainerHighest = Color(0xFFEAE1DE),
)

// La marca es clara y terrosa: por ahora solo hay esquema claro.
// TODO: tipografías Playfair Display (títulos) y Plus Jakarta Sans (texto) con Google Fonts.
@Composable
fun InsightfulTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = TerracottaLight, content = content)
}
