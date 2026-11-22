package com.insightfulgames.app.ui.play

import com.insightfulgames.app.data.model.ClocksDto
import com.insightfulgames.app.ui.Square
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class MoveInputTest {

    private val start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    private val startMoves = mapOf(
        "b1" to listOf("a3", "c3"),
        "e2" to listOf("e3", "e4"),
        "g1" to listOf("f3", "h3"),
    )
    private fun sq(name: String) = MoveInput.squareOf(name)!!

    @Test
    fun squareNamesRoundTrip() {
        assertEquals(Square(row = 7, col = 0), sq("a1"))
        assertEquals(Square(row = 0, col = 7), sq("h8"))
        assertEquals(Square(row = 4, col = 4), sq("e4"))
        for (name in listOf("a1", "e4", "h8", "d5")) assertEquals(name, MoveInput.nameOf(sq(name)))
        assertNull(MoveInput.squareOf("i9"))
        assertNull(MoveInput.squareOf("e"))
    }

    @Test
    fun targetsComeFromLegalMoves() {
        assertEquals(setOf(sq("e3"), sq("e4")), MoveInput.targets(startMoves, sq("e2")))
        assertTrue(MoveInput.targets(startMoves, sq("e7")).isEmpty())
    }

    @Test
    fun tapSelectsOnlyPiecesWithMoves() {
        assertEquals(Tap.Select(sq("e2")), MoveInput.onTap(startMoves, start, null, sq("e2")))
        assertEquals(Tap.Clear, MoveInput.onTap(startMoves, start, null, sq("e7"))) // negras no mueven
        assertEquals(Tap.Clear, MoveInput.onTap(startMoves, start, null, sq("e4"))) // casilla vacía
    }

    @Test
    fun tapOnTargetMovesAndElsewhereReselectsOrClears() {
        assertEquals(Tap.Move(sq("e2"), sq("e4"), false), MoveInput.onTap(startMoves, start, sq("e2"), sq("e4")))
        assertEquals(Tap.Select(sq("g1")), MoveInput.onTap(startMoves, start, sq("e2"), sq("g1")))
        assertEquals(Tap.Clear, MoveInput.onTap(startMoves, start, sq("e2"), sq("e2")))
        assertEquals(Tap.Clear, MoveInput.onTap(startMoves, start, sq("e2"), sq("e5")))
    }

    @Test
    fun promotionIsDetectedForBothColors() {
        val fen = "8/4P3/8/8/8/8/3p4/k6K w - - 0 1"
        assertTrue(MoveInput.isPromotion(fen, sq("e7"), sq("e8")))
        assertTrue(MoveInput.isPromotion(fen, sq("d2"), sq("d1")))
        assertFalse(MoveInput.isPromotion(fen, sq("h1"), sq("h2")))
        assertFalse(MoveInput.isPromotion(start, sq("e2"), sq("e4")))

        val tap = MoveInput.onTap(mapOf("e7" to listOf("e8")), fen, sq("e7"), sq("e8"))
        assertEquals(Tap.Move(sq("e7"), sq("e8"), true), tap)
        assertEquals("e7e8q", MoveInput.uci(sq("e7"), sq("e8"), 'Q'))
        assertEquals("e2e4", MoveInput.uci(sq("e2"), sq("e4")))
    }

    @Test
    fun remainingTimeCountsDownOnlyForTheSideToMove() {
        val now = Instant.parse("2026-11-21T10:00:00Z")
        val clocks = ClocksDto(
            white = 600_000, black = 540_000,
            turnStartedAt = "2026-11-21T09:59:30Z", deadline = "2026-11-21T10:09:30Z",
        )
        assertEquals(570_000L, MoveInput.remainingMs(clocks, "white", "white", "in_progress", now))
        assertEquals(540_000L, MoveInput.remainingMs(clocks, "black", "white", "in_progress", now))
        // Vencido: nunca negativo
        assertEquals(0L, MoveInput.remainingMs(clocks, "white", "white", "in_progress", now.plusSeconds(3600)))
        // Terminada: se muestra lo guardado
        assertEquals(600_000L, MoveInput.remainingMs(clocks, "white", "white", "finished", now))
        assertNull(MoveInput.remainingMs(null, "white", "white", "in_progress", now))
    }

    @Test
    fun clockTextRoundsUp() {
        assertEquals("10:00", MoveInput.clockText(600_000))
        assertEquals("0:01", MoveInput.clockText(1))
        assertEquals("0:00", MoveInput.clockText(0))
        assertEquals("1:05", MoveInput.clockText(64_500))
    }
}
