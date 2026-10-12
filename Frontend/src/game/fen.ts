import type { Color } from './types';

// Lectura de FEN para pintar el tablero. Aquí no hay reglas de ajedrez:
// la legalidad de las jugadas la decide Game Logic.

export type PieceType = 'k' | 'q' | 'r' | 'b' | 'n' | 'p';

export interface Piece {
  color: Color;
  type: PieceType;
}

/** 8 filas, de la fila 8 a la 1; cada una con las columnas de la a a la h. */
export type BoardGrid = (Piece | null)[][];

export const FILES = 'abcdefgh';

const PIECE_TYPES = 'kqrbnp';

export function parseFen(fen: string): BoardGrid {
  const rows = fen.trim().split(/\s+/)[0].split('/');
  return Array.from({ length: 8 }, (_, rankIndex) => {
    const row: (Piece | null)[] = [];
    for (const char of rows[rankIndex] ?? '') {
      const type = char.toLowerCase();
      if (char >= '1' && char <= '8') {
        for (let i = 0; i < Number(char); i++) row.push(null);
      } else if (PIECE_TYPES.includes(type)) {
        row.push({ color: char === type ? 'black' : 'white', type: type as PieceType });
      } else {
        row.push(null);
      }
    }
    while (row.length < 8) row.push(null);
    return row.slice(0, 8);
  });
}

export function squareName(fileIndex: number, rankIndex: number): string {
  return `${FILES[fileIndex]}${8 - rankIndex}`;
}

export function pieceAt(grid: BoardGrid, square: string): Piece | null {
  const fileIndex = FILES.indexOf(square[0]);
  const rankIndex = 8 - Number(square[1]);
  return grid[rankIndex]?.[fileIndex] ?? null;
}

/** El UCI de una coronación exige la pieza elegida (e7e8q), así que hay que detectarla. */
export function isPromotion(piece: Piece, target: string): boolean {
  return piece.type === 'p' && target[1] === (piece.color === 'white' ? '8' : '1');
}
