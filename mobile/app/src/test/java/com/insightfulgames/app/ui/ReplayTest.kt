package com.insightfulgames.app.ui

import com.insightfulgames.app.data.model.MoveDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ReplayTest {

    private fun move(ply: Int, san: String, uci: String, fenAfter: String? = "fen-$ply", color: String? = null) =
        MoveDto(ply = ply, color = color, san = san, uci = uci, fenAfter = fenAfter)

    private val italian = listOf(
        move(1, "e4", "e2e4"),
        move(2, "e5", "e7e5"),
        move(3, "Nf3", "g1f3"),
        move(4, "Nc6", "b8c6"),
        move(5, "Bc4", "f1c4"),
    )

    // ---- posiciones: N jugadas => N+1 posiciones ----

    @Test fun startsAtInitialFenAndEndsAtLastMove() {
        val replay = buildReplay("initial", italian)!!
        assertEquals(5, replay.lastPly)
        assertEquals("initial", replay.fenAt(0))
        assertEquals("fen-1", replay.fenAt(1))
        assertEquals("fen-5", replay.fenAt(5))
    }

    @Test fun usesStandardStartWhenInitialFenIsMissing() {
        assertEquals(START_FEN, buildReplay(null, italian)!!.fenAt(0))
        assertEquals(START_FEN, buildReplay("  ", italian)!!.fenAt(0))
    }

    @Test fun clampsOutOfRangePly() {
        val replay = buildReplay(null, italian)!!
        assertEquals(0, replay.clamp(-3))
        assertEquals(5, replay.clamp(99))
        assertEquals("fen-5", replay.fenAt(99))
    }

    @Test fun lastMoveIsNullAtStart() {
        val replay = buildReplay(null, italian)!!
        assertNull(replay.moveAt(0))
        assertEquals("e4", replay.moveAt(1)!!.san)
        assertEquals("Bc4", replay.moveAt(5)!!.san)
    }

    @Test fun gameWithoutMovesHasOnlyTheStartingPosition() {
        val replay = buildReplay(null, emptyList())!!
        assertEquals(0, replay.lastPly)
        assertEquals(START_FEN, replay.fenAt(0))
        assertNull(replay.moveAt(0))
    }

    @Test fun movesAreOrderedByPly() {
        val replay = buildReplay(null, italian.reversed())!!
        assertEquals("e4", replay.moveAt(1)!!.san)
        assertEquals("fen-2", replay.fenAt(2))
    }

    @Test fun noReplayIfAMoveHasNoFenAfter() {
        val moves = listOf(move(1, "e4", "e2e4"), move(2, "e5", "e7e5", fenAfter = null))
        assertNull(buildReplay(null, moves))
    }

    // ---- casillas de la última jugada ----

    @Test fun uciSquaresUseBoardCoordinates() {
        // fila 0 = octava fila; columna 0 = "a"
        assertEquals(Square(6, 4) to Square(4, 4), uciSquares("e2e4"))
        assertEquals(Square(7, 6) to Square(5, 5), uciSquares("g1f3"))
        assertEquals(Square(1, 4) to Square(0, 4), uciSquares("e7e8q")) // promoción
    }

    @Test fun uciSquaresRejectsInvalidMoves() {
        assertNull(uciSquares(""))
        assertNull(uciSquares("e2"))
        assertNull(uciSquares("i2e4"))
        assertNull(uciSquares("e9e4"))
    }

    // ---- lista de jugadas ----

    @Test fun groupsMovesIntoRows() {
        val rows = moveRows(italian)
        assertEquals(3, rows.size)
        assertEquals(MoveRow(1, MoveCell(1, "e4"), MoveCell(2, "e5")), rows[0])
        assertEquals(MoveRow(2, MoveCell(3, "Nf3"), MoveCell(4, "Nc6")), rows[1])
        assertEquals(MoveRow(3, MoveCell(5, "Bc4"), null), rows[2])
    }

    @Test fun usesExplicitColorWhenPresent() {
        val rows = moveRows(listOf(move(1, "e4", "e2e4", color = "white"), move(2, "e5", "e7e5", color = "black")))
        assertEquals(1, rows.size)
        assertEquals("e5", rows[0].black!!.san)
    }

    @Test fun rowStartingWithBlackKeepsItsNumber() {
        val rows = moveRows(listOf(move(2, "e5", "e7e5"), move(3, "Nf3", "g1f3")))
        assertEquals(MoveRow(1, null, MoveCell(1, "e5")), rows[0])
        assertEquals(MoveRow(2, MoveCell(2, "Nf3"), null), rows[1])
    }

    @Test fun findsTheRowOfEachPosition() {
        val rows = moveRows(italian)
        assertEquals(-1, moveRowIndex(rows, 0))
        assertEquals(0, moveRowIndex(rows, 1))
        assertEquals(0, moveRowIndex(rows, 2))
        assertEquals(1, moveRowIndex(rows, 3))
        assertEquals(2, moveRowIndex(rows, 5))
    }

    // ---- texto bajo el tablero ----

    @Test fun captionAtStartAndAfterMoves() {
        assertEquals("Posición inicial · 0 / 5", GameLabels.replayCaption(0, 5, null))
        assertEquals("1. e4 · 1 / 5", GameLabels.replayCaption(1, 5, italian[0]))
        assertEquals("1... e5 · 2 / 5", GameLabels.replayCaption(2, 5, italian[1]))
        assertEquals("2. Nf3 · 3 / 5", GameLabels.replayCaption(3, 5, italian[2]))
    }
}
