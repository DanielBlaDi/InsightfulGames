import type { GameTransport } from '../session';
import type {
  ClientMessage,
  Color,
  EndReason,
  GameMove,
  GameResult,
  GameState,
  Participant,
  PromotionPiece,
  ServerMessage,
} from '../types';
import type { MockPly, MockScenario, Scripted } from './scenarios';

const BOT_DELAY_MS = 1200;
const MOCK_USER = '00000000-0000-4000-8000-000000000001';

interface Outcome {
  result: GameResult;
  endReason: EndReason;
}

const turnOf = (fen: string): Color => (fen.split(' ')[1] === 'b' ? 'black' : 'white');

/**
 * Sustituto de Single Player: responde con los mensajes del contrato siguiendo un guion.
 * Una jugada fuera del guion se rechaza con `move_rejected`, aunque estuviera resaltada.
 */
export function createMockTransport(scenario: MockScenario, gameId = `mock-${scenario.id}`): GameTransport {
  let listener: ((message: ServerMessage) => void) | null = null;
  const timers = new Set<ReturnType<typeof setTimeout>>();

  const createdAt = new Date().toISOString();
  const moves: GameMove[] = [];
  const promotions: PromotionPiece[] = [];
  let fen = scenario.initialFen;
  let legalMoves = scenario.initialLegalMoves;
  let outcome: Outcome | null = null;
  let finishedAt: string | null = null;
  // Sube con cada cambio, como en Game Logic (sección 19).
  let version = 1;

  const emit = (message: ServerMessage) => listener?.(message);
  // Lectura indirecta: TypeScript no sigue las asignaciones hechas desde finish().
  const ended = (): Outcome | null => outcome;
  const resolve = (value: Scripted) => (typeof value === 'string' ? value : value(promotions));

  const later = (action: () => void, delay: number) => {
    const id = setTimeout(() => {
      timers.delete(id);
      action();
    }, delay);
    timers.add(id);
  };

  const participants = (): Participant[] =>
    scenario.mode === 'vs_bot'
      ? [{ userId: MOCK_USER, color: scenario.playerColor ?? 'white' }]
      : [
          { userId: MOCK_USER, color: 'white' },
          { userId: MOCK_USER, color: 'black' },
        ];

  const snapshot = (): GameState => ({
    gameId,
    mode: scenario.mode,
    visibility: 'private',
    matchId: null,
    participants: participants(),
    botLevel: scenario.botLevel,
    timeControl: null,
    clocks: null,
    status: outcome ? 'finished' : 'in_progress',
    turn: turnOf(fen),
    fen,
    initialFen: scenario.initialFen,
    legalMoves: outcome ? {} : legalMoves,
    moves: [...moves],
    drawOffer: null,
    version,
    result: outcome?.result ?? null,
    endReason: outcome?.endReason ?? null,
    createdAt,
    finishedAt,
  });

  const finish = (result: GameResult, endReason: EndReason) => {
    outcome = { result, endReason };
    finishedAt = new Date().toISOString();
  };

  const emitGameOver = () => {
    const result = ended();
    if (result) emit({ type: 'game_over', ...result });
  };

  const applyPly = (ply: MockPly, uci: string) => {
    if (outcome) return; // el jugador abandonó mientras el bot pensaba
    if (ply.promotes) promotions.push(uci[4] as PromotionPiece);
    const color = turnOf(fen);
    fen = resolve(ply.fenAfter);
    version += 1;
    legalMoves = ply.legalMovesAfter;
    moves.push({
      ply: moves.length + 1,
      color,
      san: resolve(ply.san),
      uci,
      fenAfter: fen,
      timestamp: new Date().toISOString(),
    });
    if (moves.length === scenario.plies.length && scenario.outcome) {
      finish(scenario.outcome.result, scenario.outcome.endReason);
    }
    emit({ type: 'state', state: snapshot(), lastMove: uci });
    emitGameOver();
  };

  const reject = (code: string, message: string) => emit({ type: 'move_rejected', code, message });

  const handleMove = (uci: string, expectedVersion: number) => {
    if (outcome) return reject('GAME_FINISHED', 'La partida ya terminó.');
    if (expectedVersion !== version) {
      return reject('VERSION_CONFLICT', 'La partida cambió mientras jugabas. Se muestra la posición actual.');
    }
    if (scenario.mode === 'vs_bot' && turnOf(fen) !== scenario.playerColor) {
      return reject('NOT_YOUR_TURN', 'Es el turno de Botcito.');
    }
    const next = scenario.plies[moves.length];
    if (!next) {
      return reject('INVALID_MOVE', 'Simulación: el guion de esta partida ya no tiene más jugadas.');
    }
    const matches = next.promotes
      ? uci.length === 5 && uci.slice(0, 4) === next.uci && 'qrbn'.includes(uci[4])
      : uci === next.uci;
    if (!matches) {
      return reject('INVALID_MOVE', `Simulación: el guion solo continúa con ${next.uci}.`);
    }

    applyPly(next, uci);

    const reply = scenario.plies[moves.length];
    if (!ended() && reply?.by === 'bot') {
      emit({ type: 'bot_thinking' });
      later(() => applyPly(reply, reply.uci), BOT_DELAY_MS);
    }
  };

  const handleResign = (side?: Color) => {
    if (outcome) return reject('GAME_FINISHED', 'La partida ya terminó.');
    const loser = scenario.playerColor ?? side ?? turnOf(fen);
    finish(loser === 'white' ? 'black' : 'white', 'surrender');
    version += 1;
    emit({ type: 'state', state: snapshot() });
    emitGameOver();
  };

  // Contrato, sección 6: si el jugador lleva negras, la partida se crea con la primera jugada del bot.
  const opening = scenario.plies[0];
  if (opening?.by === 'bot') applyPly(opening, opening.uci);

  return {
    connect({ onOpen, onMessage }) {
      listener = onMessage;
      // Al conectarse, el servidor envía un `state` completo sin lastMove.
      later(() => {
        onOpen();
        emit({ type: 'state', state: snapshot() });
      }, 0);
    },
    send(message: ClientMessage) {
      if (message.type === 'move') handleMove(message.uci, message.expectedVersion);
      else handleResign(message.side);
    },
    close() {
      timers.forEach(clearTimeout);
      timers.clear();
      listener = null;
    },
  };
}
