package com.insightfulgames.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class FenParserTest {
    private val start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    @Test fun parsesStartingPosition() {
        val board = parseFenPlacement(start)!!
        assertEquals(8, board.size)
        assertEquals('r', board[0][0])
        assertEquals('k', board[0][4])
        assertNull(board[3][3])
        assertEquals('P', board[6][0])
        assertEquals('K', board[7][4])
    }

    @Test fun rejectsInvalidFen() {
        assertNull(parseFenPlacement(""))
        assertNull(parseFenPlacement("8/8/8"))
        assertNull(parseFenPlacement("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN w - - 0 1")) // fila corta
        assertNull(parseFenPlacement("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNX w - - 0 1")) // pieza inválida
    }

    @Test fun glyphsForceTextPresentation() {
        assertEquals("\u265F\uFE0E", pieceGlyph('p'))
        assertEquals("\u265A\uFE0E", pieceGlyph('K'))
    }
}
