import type { GameTransport } from '../session';
import type {
  ClientMessage,
  Color,
  EndReason,
  GameMove,
  GameResult,
  GameState,
  PromotionPiece,
  ServerMessage,
} from '../types';
import type { MockPly, MockScenario, Scripted } from './scenarios';

const BOT_DELAY_MS = 1200;

interface Outcome {
  result: GameResult;
  endReason: EndReason;
}

const turnOf = (fen: string): Color => (fen.split(' ')[1] === 'b' ? 'black' : 'white');

/**
 * Sustituto de Single Player: responde con los mensajes del contrato siguiendo un guion.
 * Una jugada fuera del guion se rechaza con `move_rejected`, aunque estuviera resaltada.
 */
export function createMockTransport(scenario: MockScenario): GameTransport {
  let listener: ((message: ServerMessage) => void) | null = null;
  const timers = new Set<ReturnType<typeof setTimeout>>();

  const createdAt = new Date().toISOString();
  const moves: GameMove[] = [];
  const promotions: PromotionPiece[] = [];
  let fen = scenario.initialFen;
  let legalMoves = scenario.initialLegalMoves;
  let outcome: Outcome | null = null;
  let finishedAt: string | null = null;

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

  const snapshot = (): GameState => ({
    gameId: `mock-${scenario.id}`,
    userId: 'mock-user',
    mode: scenario.mode,
    botLevel: scenario.botLevel,
    playerColor: scenario.playerColor,
    status: outcome ? 'finished' : 'in_progress',
    turn: turnOf(fen),
    fen,
    legalMoves: outcome ? {} : legalMoves,
    moves: [...moves],
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
    fen = resolve(ply.fenAfter);
    legalMoves = ply.legalMovesAfter;
    moves.push({
      ply: moves.length + 1,
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

  const handleMove = (uci: string) => {
    if (outcome) return reject('GAME_FINISHED', 'La partida ya terminó.');
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
    finish(loser === 'white' ? 'black' : 'white', 'resignation');
    emit({ type: 'state', state: snapshot() });
    emitGameOver();
  };

  return {
    connect(onMessage) {
      listener = onMessage;
      // Al conectarse, el servidor envía un `state` completo sin lastMove.
      later(() => emit({ type: 'state', state: snapshot() }), 0);
    },
    send(message: ClientMessage) {
      if (message.type === 'move') handleMove(message.uci);
      else handleResign(message.side);
    },
    close() {
      timers.forEach(clearTimeout);
      timers.clear();
      listener = null;
    },
  };
}
