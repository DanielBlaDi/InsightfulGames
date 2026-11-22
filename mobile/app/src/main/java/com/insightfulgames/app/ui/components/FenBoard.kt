package com.insightfulgames.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
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
import com.insightfulgames.app.ui.Square
import com.insightfulgames.app.ui.parseFenPlacement
import com.insightfulgames.app.ui.pieceGlyph

private val LightSquare = Color(0xFFF0D9B5)
private val DarkSquare = Color(0xFFB58863)
private val BlackPiece = Color(0xFF1F1B1A)
private val LightSquareMoved = Color(0xFFF7EC74)
private val DarkSquareMoved = Color(0xFFDAC34B)
private val SelectedSquare = Color(0xFF8FB46A)
private val TargetDot = Color(0x55000000)

/**
 * Tablero a partir de una FEN. Blancas abajo (salvo [flipped]). No dibuja nada si la FEN no es válida.
 * [lastMove] (origen, destino) pinta de amarillo la última jugada, como en chess.com.
 * Sin [onSquareClick] es de solo lectura; con él, [selected] se resalta y [targets] llevan un punto.
 */
@Composable
fun FenBoard(
    fen: String?,
    modifier: Modifier = Modifier,
    lastMove: Pair<Square, Square>? = null,
    selected: Square? = null,
    targets: Set<Square> = emptySet(),
    flipped: Boolean = false,
    onSquareClick: ((Square) -> Unit)? = null,
) {
    val board = remember(fen) { fen?.let { parseFenPlacement(it) } } ?: return
    val marked = remember(lastMove) { lastMove?.let { setOf(it.first, it.second) } ?: emptySet() }

    Column(
        modifier
            .fillMaxWidth()
            .aspectRatio(1f)
            .border(1.dp, MaterialTheme.colorScheme.outline),
    ) {
        for (displayRow in 0 until 8) {
            Row(Modifier.weight(1f).fillMaxWidth()) {
                for (displayCol in 0 until 8) {
                    val r = if (flipped) 7 - displayRow else displayRow
                    val c = if (flipped) 7 - displayCol else displayCol
                    val square = Square(r, c)
                    val dark = (r + c) % 2 == 1
                    val squareColor = when {
                        square == selected -> SelectedSquare
                        square in marked -> if (dark) DarkSquareMoved else LightSquareMoved
                        dark -> DarkSquare
                        else -> LightSquare
                    }
                    Box(
                        Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .background(squareColor)
                            .then(if (onSquareClick != null) Modifier.clickable { onSquareClick(square) } else Modifier),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (square in targets) {
                            Box(
                                Modifier
                                    .fillMaxSize()
                                    .padding(if (board[r][c] == null) 14.dp else 2.dp)
                                    .background(TargetDot, CircleShape),
                            )
                        }
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
