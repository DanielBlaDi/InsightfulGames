import type { Color, EndReason, GameMode, GameResult, LegalMoves, PromotionPiece } from '../types';

// Partidas guionizadas para probar la pantalla sin backend. Las posiciones y las
// jugadas legales están escritas a mano: el simulador no calcula reglas.

/** Texto fijo, o dependiente de las piezas de coronación elegidas hasta el momento. */
export type Scripted = string | ((promotions: PromotionPiece[]) => string);

export interface MockPly {
  uci: string; // sin sufijo de coronación si `promotes`
  san: Scripted;
  fenAfter: Scripted;
  legalMovesAfter: LegalMoves;
  by?: 'bot';
  promotes?: true;
}

export interface MockScenario {
  id: string;
  label: string;
  mode: GameMode;
  botLevel: number | null;
  playerColor: Color | null;
  initialFen: string;
  initialLegalMoves: LegalMoves;
  plies: MockPly[];
  outcome?: { result: GameResult; endReason: EndReason };
}

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const pawnPushes = (rank: 2 | 7, files = 'abcdefgh'): LegalMoves =>
  Object.fromEntries(
    [...files].map((f) => [`${f}${rank}`, rank === 2 ? [`${f}3`, `${f}4`] : [`${f}6`, `${f}5`]]),
  );

const WHITE_START: LegalMoves = { ...pawnPushes(2), b1: ['a3', 'c3'], g1: ['f3', 'h3'] };
const BLACK_START: LegalMoves = { ...pawnPushes(7), b8: ['a6', 'c6'], g8: ['f6', 'h6'] };

const foolsMate: MockScenario = {
  id: 'local-mate',
  label: 'Local · mate del loco',
  mode: 'local',
  botLevel: null,
  playerColor: null,
  initialFen: START_FEN,
  initialLegalMoves: WHITE_START,
  plies: [
    {
      uci: 'f2f3',
      san: 'f3',
      fenAfter: 'rnbqkbnr/pppppppp/8/8/8/5P2/PPPPP1PP/RNBQKBNR b KQkq - 0 1',
      legalMovesAfter: BLACK_START,
    },
    {
      uci: 'e7e5',
      san: 'e5',
      fenAfter: 'rnbqkbnr/pppp1ppp/8/4p3/8/5P2/PPPPP1PP/RNBQKBNR w KQkq e6 0 2',
      legalMovesAfter: {
        ...pawnPushes(2, 'abcdegh'),
        f3: ['f4'],
        b1: ['a3', 'c3'],
        g1: ['h3'],
        e1: ['f2'],
      },
    },
    {
      uci: 'g2g4',
      san: 'g4',
      fenAfter: 'rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq g3 0 2',
      legalMovesAfter: {
        ...pawnPushes(7, 'abcdfgh'),
        e5: ['e4'],
        b8: ['a6', 'c6'],
        g8: ['e7', 'f6', 'h6'],
        f8: ['e7', 'd6', 'c5', 'b4', 'a3'],
        d8: ['e7', 'f6', 'g5', 'h4'],
        e8: ['e7'],
      },
    },
    {
      uci: 'd8h4',
      san: 'Qh4#',
      fenAfter: 'rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3',
      legalMovesAfter: {},
    },
  ],
  outcome: { result: 'black', endReason: 'checkmate' },
};

const vsBot: MockScenario = {
  id: 'vs-bot',
  label: 'Contra Botcito · apertura italiana',
  mode: 'vs_bot',
  botLevel: 8,
  playerColor: 'white',
  initialFen: START_FEN,
  initialLegalMoves: WHITE_START,
  plies: [
    {
      uci: 'e2e4',
      san: 'e4',
      fenAfter: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      legalMovesAfter: BLACK_START,
    },
    {
      by: 'bot',
      uci: 'e7e5',
      san: 'e5',
      fenAfter: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2',
      legalMovesAfter: {
        ...pawnPushes(2, 'abcdfgh'),
        b1: ['a3', 'c3'],
        g1: ['e2', 'f3', 'h3'],
        f1: ['e2', 'd3', 'c4', 'b5', 'a6'],
        d1: ['e2', 'f3', 'g4', 'h5'],
        e1: ['e2'],
      },
    },
    {
      uci: 'g1f3',
      san: 'Nf3',
      fenAfter: 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2',
      legalMovesAfter: {
        ...pawnPushes(7, 'abcdfgh'),
        b8: ['a6', 'c6'],
        g8: ['e7', 'f6', 'h6'],
        f8: ['e7', 'd6', 'c5', 'b4', 'a3'],
        d8: ['e7', 'f6', 'g5', 'h4'],
        e8: ['e7'],
      },
    },
    {
      by: 'bot',
      uci: 'b8c6',
      san: 'Nc6',
      fenAfter: 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3',
      legalMovesAfter: {
        ...pawnPushes(2, 'abcdgh'),
        b1: ['a3', 'c3'],
        f3: ['d4', 'e5', 'g5', 'h4', 'g1'],
        f1: ['e2', 'd3', 'c4', 'b5', 'a6'],
        d1: ['e2'],
        e1: ['e2'],
        h1: ['g1'],
      },
    },
    {
      uci: 'f1c4',
      san: 'Bc4',
      fenAfter: 'r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3',
      legalMovesAfter: {
        ...pawnPushes(7, 'abdfgh'),
        c6: ['b8', 'e7', 'a5', 'b4', 'd4'],
        g8: ['e7', 'f6', 'h6'],
        f8: ['e7', 'd6', 'c5', 'b4', 'a3'],
        d8: ['e7', 'f6', 'g5', 'h4'],
        e8: ['e7'],
        a8: ['b8'],
      },
    },
    {
      by: 'bot',
      uci: 'f8c5',
      san: 'Bc5',
      fenAfter: 'r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4',
      legalMovesAfter: {
        ...pawnPushes(2, 'abdgh'),
        c2: ['c3'],
        b1: ['a3', 'c3'],
        f3: ['d4', 'e5', 'g5', 'h4', 'g1'],
        c4: ['b3', 'd3', 'e2', 'f1', 'b5', 'a6', 'd5', 'e6', 'f7'],
        d1: ['e2'],
        e1: ['e2', 'f1', 'g1'],
        h1: ['g1', 'f1'],
      },
    },
    {
      uci: 'e1g1',
      san: 'O-O',
      fenAfter: 'r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 4',
      legalMovesAfter: {
        ...pawnPushes(7, 'abdfgh'),
        c6: ['b8', 'e7', 'a5', 'b4', 'd4'],
        g8: ['e7', 'f6', 'h6'],
        c5: ['b6', 'd6', 'e7', 'f8', 'b4', 'a3', 'd4', 'e3', 'f2'],
        d8: ['e7', 'f6', 'g5', 'h4'],
        e8: ['e7', 'f8'],
        a8: ['b8'],
      },
    },
    {
      by: 'bot',
      uci: 'g8f6',
      san: 'Nf6',
      fenAfter: 'r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 w kq - 6 5',
      legalMovesAfter: {
        ...pawnPushes(2, 'abdgh'),
        c2: ['c3'],
        b1: ['a3', 'c3'],
        f3: ['d4', 'e5', 'g5', 'h4', 'e1'],
        c4: ['b3', 'd3', 'e2', 'b5', 'a6', 'd5', 'e6', 'f7'],
        d1: ['e2', 'e1'],
        f1: ['e1'],
        g1: ['h1'],
      },
    },
  ],
};

const KING_C3 = ['b2', 'b3', 'b4', 'c2', 'c4', 'd2', 'd3', 'd4'];

const promotion: MockScenario = {
  id: 'promotion',
  label: 'Local · coronación de ambos bandos',
  mode: 'local',
  botLevel: null,
  playerColor: null,
  initialFen: '8/P6k/8/8/8/2K5/7p/8 w - - 0 1',
  initialLegalMoves: { a7: ['a8'], c3: KING_C3 },
  plies: [
    {
      promotes: true,
      uci: 'a7a8',
      san: ([white]) => `a8=${white.toUpperCase()}`,
      fenAfter: ([white]) => `${white.toUpperCase()}7/7k/8/8/8/2K5/7p/8 b - - 0 1`,
      legalMovesAfter: { h2: ['h1'], h7: ['g7', 'g6', 'h6'] },
    },
    {
      promotes: true,
      uci: 'h2h1',
      san: ([, black]) => `h1=${black.toUpperCase()}`,
      fenAfter: ([white, black]) => `${white.toUpperCase()}7/7k/8/8/8/2K5/8/7${black} w - - 0 2`,
      legalMovesAfter: { c3: KING_C3 },
    },
  ],
};

export const SCENARIOS: MockScenario[] = [vsBot, foolsMate, promotion];
