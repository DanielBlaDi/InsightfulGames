package com.insightfulgames.app.ui.play

import com.insightfulgames.app.data.model.ClocksDto
import com.insightfulgames.app.ui.Square
import com.insightfulgames.app.ui.parseFenPlacement
import java.time.Instant

/** Qué hacer al tocar una casilla del tablero. */
sealed interface Tap {
    /** Seleccionar una pieza propia que tiene jugadas. */
    data class Select(val square: Square) : Tap

    /** Quitar la selección (tocar la misma casilla o una casilla sin jugada). */
    data object Clear : Tap

    /** Jugar. Si [needsPromotion], hay que elegir la pieza antes de enviar. */
    data class Move(val from: Square, val to: Square, val needsPromotion: Boolean) : Tap
}

/** Entrada de jugadas sin dependencias de Android (se prueba con JUnit). */
object MoveInput {

    /** "e4" -> Square. null si no es una casilla. Fila 0 = octava fila, como en parseFenPlacement. */
    fun squareOf(name: String): Square? {
        if (name.length != 2) return null
        val file = name[0]
        val rank = name[1]
        if (file !in 'a'..'h' || rank !in '1'..'8') return null
        return Square(row = '8' - rank, col = file - 'a')
    }

    fun nameOf(square: Square): String = "${'a' + square.col}${'8' - square.row}"

    /** Destinos legales desde [from] según legalMoves del GameState. */
    fun targets(legalMoves: Map<String, List<String>>, from: Square): Set<Square> =
        legalMoves[nameOf(from)].orEmpty().mapNotNull { squareOf(it) }.toSet()

    /** ¿Mover de [from] a [to] es una coronación? Peón blanco a la octava o negro a la primera. */
    fun isPromotion(fen: String?, from: Square, to: Square): Boolean {
        val piece = fen?.let { parseFenPlacement(it) }?.getOrNull(from.row)?.getOrNull(from.col) ?: return false
        return (piece == 'P' && to.row == 0) || (piece == 'p' && to.row == 7)
    }

    /** UCI de la jugada: "e2e4" o, al coronar, "e7e8q". */
    fun uci(from: Square, to: Square, promotion: Char? = null): String =
        nameOf(from) + nameOf(to) + (promotion?.lowercaseChar()?.toString() ?: "")

    /**
     * Toque en [tapped] con [selected] seleccionada. Solo se pueden elegir casillas de origen que estén en
     * legalMoves (que ya son las del color que mueve); tocar otra pieza con jugadas cambia la selección.
     */
    fun onTap(legalMoves: Map<String, List<String>>, fen: String?, selected: Square?, tapped: Square): Tap {
        if (selected != null && selected != tapped && tapped in targets(legalMoves, selected)) {
            return Tap.Move(selected, tapped, isPromotion(fen, selected, tapped))
        }
        if (selected == tapped) return Tap.Clear
        return if (legalMoves[nameOf(tapped)].isNullOrEmpty()) Tap.Clear else Tap.Select(tapped)
    }

    /**
     * Milisegundos que le quedan a [color]. Al color que tiene el turno se le descuenta el tiempo desde que
     * empezó (deadline - ahora); al otro, lo que tenía guardado. null si ese color no tiene reloj.
     */
    fun remainingMs(clocks: ClocksDto?, color: String, turn: String?, status: String, now: Instant): Long? {
        clocks ?: return null
        val stored = if (color == "white") clocks.white else clocks.black
        stored ?: return null
        val deadline = clocks.deadline?.let { runCatching { Instant.parse(it) }.getOrNull() }
        if (status != "in_progress" || turn != color || deadline == null) return stored.coerceAtLeast(0)
        return (deadline.toEpochMilli() - now.toEpochMilli()).coerceAtLeast(0)
    }

    /** "9:59", "0:07". Redondea hacia arriba para que 0:00 solo aparezca cuando de verdad se acabó. */
    fun clockText(ms: Long): String {
        val totalSeconds = (ms.coerceAtLeast(0) + 999) / 1000
        return "%d:%02d".format(totalSeconds / 60, totalSeconds % 60)
    }
}
