import type { Piece, PieceType } from './fen';
import PieceGlyph from './PieceGlyph';

const PIECE_NAMES: Record<PieceType, string> = {
  k: 'rey',
  q: 'dama',
  r: 'torre',
  b: 'alfil',
  n: 'caballo',
  p: 'peón',
};

interface ChessSquareProps {
  square: string;
  light: boolean;
  piece: Piece | null;
  selected: boolean;
  legalTarget: boolean;
  lastMove: boolean;
  interactive: boolean;
  fileLabel?: string;
  rankLabel?: string;
  onClick: (square: string) => void;
}

export default function ChessSquare({
  square,
  light,
  piece,
  selected,
  legalTarget,
  lastMove,
  interactive,
  fileLabel,
  rankLabel,
  onClick,
}: ChessSquareProps) {
  const pieceLabel = piece
    ? `${PIECE_NAMES[piece.type]} ${piece.color === 'white' ? 'blanco' : 'negro'}`
    : 'vacía';
  const labelColor = light ? 'text-[#9c633a]' : 'text-[#e9d2b4]';

  return (
    <button
      type="button"
      aria-label={`${square}, ${pieceLabel}${legalTarget ? ', destino válido' : ''}`}
      aria-pressed={selected}
      onClick={() => onClick(square)}
      className={`relative flex items-center justify-center p-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
        light ? 'bg-[#e9d2b4]' : 'bg-[#9c633a]'
      } ${interactive ? 'cursor-pointer' : 'cursor-default'}`}
    >
      {lastMove && <span className="absolute inset-0 bg-tertiary-fixed-dim/60"></span>}
      {selected && <span className="absolute inset-0 bg-primary/35 ring-2 ring-inset ring-primary"></span>}

      {rankLabel && (
        <span className={`absolute top-0.5 left-1 text-[10px] font-mono font-bold ${labelColor}`}>{rankLabel}</span>
      )}
      {fileLabel && (
        <span className={`absolute bottom-0 right-1 text-[10px] font-mono font-bold ${labelColor}`}>{fileLabel}</span>
      )}

      {piece && <PieceGlyph piece={piece} fontSize="9.5cqw" />}

      {legalTarget &&
        (piece ? (
          <span className="absolute inset-[5%] rounded-full border-4 border-primary/75"></span>
        ) : (
          <span className="absolute w-[30%] h-[30%] rounded-full bg-[#2a170c]/35"></span>
        ))}
    </button>
  );
}
