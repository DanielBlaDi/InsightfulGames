package com.insightfulgames.app.ui

import com.insightfulgames.app.data.model.MoveDto

/** Posición inicial estándar. Se usa si la partida no trae initialFen. */
const val START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

/** Casilla del tablero tal como se dibuja: fila 0 = octava fila (negras arriba), columna 0 = columna "a". */
data class Square(val row: Int, val col: Int)

/**
 * Una partida lista para repetirla jugada a jugada (como en chess.com).
 * "ply" es cuántas jugadas se han aplicado: 0 = posición inicial, [lastPly] = posición final.
 */
class Replay(val moves: List<MoveDto>, private val positions: List<String>) {
    init {
        require(positions.size == moves.size + 1) { "Se esperan N+1 posiciones para N jugadas" }
    }

    val lastPly: Int get() = moves.size

    fun clamp(ply: Int): Int = ply.coerceIn(0, lastPly)

    /** Posición después de aplicar [ply] jugadas. */
    fun fenAt(ply: Int): String = positions[clamp(ply)]

    /** Última jugada aplicada en [ply]; null en la posición inicial. */
    fun moveAt(ply: Int): MoveDto? = if (ply in 1..lastPly) moves[ply - 1] else null
}

/**
 * Arma la repetición con initialFen y el fenAfter de cada jugada (contrato, sección 19).
 * null si alguna jugada no trae fenAfter: entonces no se puede navegar y la pantalla muestra solo la posición final.
 */
fun buildReplay(initialFen: String?, moves: List<MoveDto>): Replay? {
    val ordered = moves.sortedBy { it.ply }
    val positions = ArrayList<String>(ordered.size + 1)
    positions.add(initialFen?.takeIf { it.isNotBlank() } ?: START_FEN)
    for (move in ordered) {
        positions.add(move.fenAfter ?: return null)
    }
    return Replay(ordered, positions)
}

/** Casillas de origen y destino de una jugada UCI ("e2e4", "e7e8q"). null si no es válida. */
fun uciSquares(uci: String): Pair<Square, Square>? {
    if (uci.length < 4) return null
    val from = squareOf(uci[0], uci[1]) ?: return null
    val to = squareOf(uci[2], uci[3]) ?: return null
    return from to to
}

private fun squareOf(file: Char, rank: Char): Square? =
    if (file in 'a'..'h' && rank in '1'..'8') Square(row = '8' - rank, col = file - 'a') else null

/** v9 trae color en cada jugada; Game Logic actual no. Si falta, se deduce de ply (impar = blancas). */
fun isWhiteMove(move: MoveDto): Boolean = move.color?.let { it == "white" } ?: (move.ply % 2 == 1)

/** Una jugada dentro de la lista. [position] es el ply que se muestra al tocarla (1 = primera jugada). */
data class MoveCell(val position: Int, val san: String)

/** Una fila de la lista de jugadas: "12. Nf3 Nc6". */
data class MoveRow(val number: Int, val white: MoveCell?, val black: MoveCell?)

/** Agrupa las jugadas por número: una fila por jugada completa (blancas y negras). */
fun moveRows(moves: List<MoveDto>): List<MoveRow> {
    val rows = ArrayList<MoveRow>()
    moves.forEachIndexed { index, move ->
        val cell = MoveCell(position = index + 1, san = move.san)
        val number = (move.ply + 1) / 2
        if (isWhiteMove(move)) {
            rows.add(MoveRow(number, white = cell, black = null))
        } else {
            val last = rows.lastOrNull()
            if (last != null && last.number == number && last.black == null) {
                rows[rows.lastIndex] = last.copy(black = cell)
            } else {
                rows.add(MoveRow(number, white = null, black = cell))
            }
        }
    }
    return rows
}

/** Índice de la fila que contiene la jugada mostrada en [ply]; -1 en la posición inicial. */
fun moveRowIndex(rows: List<MoveRow>, ply: Int): Int =
    rows.indexOfFirst { it.white?.position == ply || it.black?.position == ply }
