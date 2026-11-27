import { useMemo, useState } from 'react';
import ChessSquare from './ChessSquare';
import PieceGlyph from './PieceGlyph';
import { FILES, isPromotion, parseFen, pieceAt, squareName } from './fen';
import type { Color, LegalMoves, PromotionPiece } from './types';

const PROMOTION_PIECES: { type: PromotionPiece; label: string }[] = [
  { type: 'q', label: 'Dama' },
  { type: 'r', label: 'Torre' },
  { type: 'b', label: 'Alfil' },
  { type: 'n', label: 'Caballo' },
];

const INDEXES = [0, 1, 2, 3, 4, 5, 6, 7];

interface ChessBoardProps {
  fen: string;
  legalMoves: LegalMoves;
  orientation: Color;
  lastMove?: string | null;
  disabled?: boolean;
  onMove: (uci: string) => void;
}

/**
 * Tablero controlado: pinta el FEN que recibe y avisa de la jugada elegida en UCI.
 * No aplica la jugada ni conoce el canal por el que se envía.
 */
export default function ChessBoard({
  fen,
  legalMoves,
  orientation,
  lastMove = null,
  disabled = false,
  onMove,
}: ChessBoardProps) {
  const grid = useMemo(() => parseFen(fen), [fen]);
  // La selección se guarda junto al FEN en el que se hizo: si la posición cambia, caduca sola.
  const [selection, setSelection] = useState<{ fen: string; square: string } | null>(null);
  const [promotion, setPromotion] = useState<{ fen: string; from: string; to: string; color: Color } | null>(null);

  const selected = !disabled && selection?.fen === fen ? selection.square : null;
  const pendingPromotion = !disabled && promotion?.fen === fen ? promotion : null;
  const targets = selected ? (legalMoves[selected] ?? []) : [];
  const lastFrom = lastMove?.slice(0, 2);
  const lastTo = lastMove?.slice(2, 4);

  const order = orientation === 'white' ? INDEXES : [...INDEXES].reverse();

  const handleSquareClick = (square: string) => {
    if (disabled) return;

    if (selected && targets.includes(square)) {
      const piece = pieceAt(grid, selected);
      if (piece && isPromotion(piece, square)) {
        setPromotion({ fen, from: selected, to: square, color: piece.color });
      } else {
        onMove(selected + square);
      }
      setSelection(null);
      return;
    }

    const canSelect = square !== selected && (legalMoves[square]?.length ?? 0) > 0;
    setSelection(canSelect ? { fen, square } : null);
  };

  const handlePromotion = (piece: PromotionPiece) => {
    if (!pendingPromotion) return;
    onMove(pendingPromotion.from + pendingPromotion.to + piece);
    setPromotion(null);
  };

  return (
    <div className="p-3 sm:p-4 rounded-2xl bg-[#52331c] shadow-[0_16px_36px_rgba(40,16,6,0.35)] border border-[#784c2b] w-full max-w-[560px]">
      <div
        className="relative aspect-square grid grid-cols-8 grid-rows-8 border-2 border-[#3b1f0d] rounded-lg overflow-hidden shadow-inner select-none"
        style={{ containerType: 'inline-size' }}
      >
        {order.map((rankIndex, row) =>
          order.map((fileIndex, column) => {
            const square = squareName(fileIndex, rankIndex);
            return (
              <ChessSquare
                key={square}
                square={square}
                light={(fileIndex + rankIndex) % 2 === 0}
                piece={grid[rankIndex][fileIndex]}
                selected={square === selected}
                legalTarget={targets.includes(square)}
                lastMove={square === lastFrom || square === lastTo}
                interactive={!disabled && (targets.includes(square) || (legalMoves[square]?.length ?? 0) > 0)}
                fileLabel={row === 7 ? FILES[fileIndex] : undefined}
                rankLabel={column === 0 ? String(8 - rankIndex) : undefined}
                onClick={handleSquareClick}
              />
            );
          }),
        )}

        {pendingPromotion && (
          <div
            className="absolute inset-0 z-10 flex items-center justify-center bg-[#2a170c]/55 backdrop-blur-[1px]"
            onClick={() => setPromotion(null)}
          >
            <div
              role="dialog"
              aria-label="Elegir pieza de coronación"
              className="rounded-2xl bg-surface p-space-sm shadow-[0_12px_32px_-4px_rgba(76,56,36,0.35)] border border-outline-variant/40 flex flex-col items-center gap-space-xs"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="font-label-md text-label-md text-on-surface-variant">
                Coronar en {pendingPromotion.to}
              </span>
              <div className="flex gap-space-xs">
                {PROMOTION_PIECES.map(({ type, label }) => (
                  <button
                    key={type}
                    type="button"
                    aria-label={label}
                    title={label}
                    onClick={() => handlePromotion(type)}
                    className="w-14 h-14 sm:w-16 sm:h-16 rounded-xl bg-[#9c633a] hover:bg-primary-container flex items-center justify-center transition-colors cursor-pointer shadow-sm"
                  >
                    <PieceGlyph piece={{ color: pendingPromotion.color, type }} fontSize="2.25rem" />
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setPromotion(null)}
                className="font-label-md text-label-md text-on-surface-variant hover:text-on-surface transition-colors cursor-pointer"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
