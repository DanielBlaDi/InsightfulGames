package com.insightfulgames.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.insightfulgames.app.ui.parseFenPlacement
import com.insightfulgames.app.ui.pieceGlyph

private val LightSquare = Color(0xFFF0D9B5)
private val DarkSquare = Color(0xFFB58863)
private val BlackPiece = Color(0xFF1F1B1A)

/** Tablero de solo lectura a partir de una FEN. Blancas abajo. No dibuja nada si la FEN no es válida. */
@Composable
fun FenBoard(fen: String?, modifier: Modifier = Modifier) {
    val board = remember(fen) { fen?.let { parseFenPlacement(it) } } ?: return

    Column(
        modifier
            .fillMaxWidth()
            .aspectRatio(1f)
            .border(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        for (r in 0 until 8) {
            Row(Modifier.weight(1f).fillMaxWidth()) {
                for (c in 0 until 8) {
                    val dark = (r + c) % 2 == 1
                    Box(
                        Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .background(if (dark) DarkSquare else LightSquare),
                        contentAlignment = Alignment.Center,
                    ) {
                        val piece = board[r][c]
                        if (piece != null) {
                            val white = piece.isUpperCase()
                            Text(
                                text = pieceGlyph(piece),
                                fontSize = 26.sp,
                                color = if (white) Color.White else BlackPiece,
                                style = TextStyle(
                                    shadow = if (white) Shadow(Color.Black, blurRadius = 4f) else null,
                                ),
                            )
                        }
                    }
                }
            }
        }
    }
}
