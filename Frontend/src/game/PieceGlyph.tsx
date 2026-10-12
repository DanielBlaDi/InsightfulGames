import type { CSSProperties } from 'react';
import type { Piece, PieceType } from './fen';

// Glifos rellenos para ambos colores; ︎ evita que el peón se pinte como emoji.
const GLYPHS: Record<PieceType, string> = {
  k: '♚︎',
  q: '♛︎',
  r: '♜︎',
  b: '♝︎',
  n: '♞︎',
  p: '♟︎',
};

const WHITE_STYLE: CSSProperties = {
  color: '#fdf6ea',
  textShadow:
    '-1px 0 #2a170c, 1px 0 #2a170c, 0 -1px #2a170c, 0 1px #2a170c, 0 3px 4px rgba(42,23,12,0.45)',
};

const BLACK_STYLE: CSSProperties = {
  color: '#2a170c',
  textShadow: '0 1px 0 rgba(255,240,220,0.35), 0 3px 4px rgba(42,23,12,0.3)',
};

interface PieceGlyphProps {
  piece: Piece;
  fontSize: string;
}

export default function PieceGlyph({ piece, fontSize }: PieceGlyphProps) {
  return (
    <span
      aria-hidden="true"
      className="relative font-serif leading-none pointer-events-none"
      style={{ ...(piece.color === 'white' ? WHITE_STYLE : BLACK_STYLE), fontSize }}
    >
      {GLYPHS[piece.type]}
    </span>
  );
}
