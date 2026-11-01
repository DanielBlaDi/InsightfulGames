package com.insightfulgames.app.ui

/** Lee la parte de colocación de una FEN. null si no es válida. fila 0 = octava fila (negras arriba). */
fun parseFenPlacement(fen: String): List<List<Char?>>? {
    val rows = fen.trim().substringBefore(' ').split('/')
    if (rows.size != 8) return null
    return rows.map { row ->
        val cells = ArrayList<Char?>(8)
        for (c in row) {
            when {
                c in '1'..'8' -> repeat(c - '0') { cells.add(null) }
                c in "pnbrqkPNBRQK" -> cells.add(c)
                else -> return null
            }
        }
        if (cells.size != 8) return null
        cells
    }
}

/** Glifo de la pieza. Se fuerza presentación de texto (U+FE0E) para que ♟ no salga como emoji. */
fun pieceGlyph(piece: Char): String {
    val base = when (piece.lowercaseChar()) {
        'k' -> "\u265A"
        'q' -> "\u265B"
        'r' -> "\u265C"
        'b' -> "\u265D"
        'n' -> "\u265E"
        else -> "\u265F"
    }
    return base + "\uFE0E"
}
