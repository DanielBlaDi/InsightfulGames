"""Cálculo del resultado de un análisis (contrato, sección 17.4.2).

El worker reconstruye las N+1 posiciones desde ``initialFen`` y las jugadas
UCI, pide una evaluación por posición y calcula ``cpLoss``, clasificación y
resumen por color.
"""

from __future__ import annotations

from typing import Any, Mapping

import chess

from app.errors import AnalysisFailure
from app.models import Evaluation, GameInput, GameMove

MATE_SCORE = 100_000

CLASSIFICATIONS = ("best", "good", "inaccuracy", "mistake", "blunder")


def _permanent(message: str, code: str | None = None) -> AnalysisFailure:
    return AnalysisFailure(message, failure_kind="permanent", code=code)


def parse_game_input(
    data: Mapping[str, Any], expected_game_id: str | None = None
) -> GameInput:
    """Valida y reconstruye la partida devuelta por Game Logic.

    Cualquier FEN inválida, jugada ilegal o dato incoherente es un fallo
    permanente (sección 16.4.3).
    """
    if not isinstance(data, Mapping):
        raise _permanent("Game Logic devolvió un análisis de entrada inválido.")

    game_id = data.get("gameId")
    if not isinstance(game_id, str) or not game_id.strip():
        raise _permanent("El análisis de entrada no incluye gameId.")
    if expected_game_id is not None and game_id != expected_game_id:
        raise _permanent("El análisis de entrada corresponde a otra partida.")

    status = data.get("status")
    if status is not None and status != "finished":
        raise _permanent("La partida entregada por Game Logic no está terminada.")

    initial_fen = data.get("initialFen")
    if not isinstance(initial_fen, str) or not initial_fen.strip():
        raise _permanent("El análisis de entrada no incluye initialFen.")

    raw_moves = data.get("moves")
    if not isinstance(raw_moves, list) or not raw_moves:
        raise _permanent("La partida no tiene jugadas para analizar.")

    try:
        board = chess.Board(initial_fen)
    except ValueError as exc:
        raise _permanent("La FEN inicial de la partida no es válida.") from exc
    if not board.is_valid():
        raise _permanent("La FEN inicial de la partida no es válida.")

    positions = [board.fen()]
    terminal_mate = [board.is_checkmate()]
    moves: list[GameMove] = []

    for index, raw_move in enumerate(raw_moves, start=1):
        if isinstance(raw_move, str):
            uci = raw_move
            ply = index
            provided_san = None
        elif isinstance(raw_move, Mapping):
            uci = raw_move.get("uci")
            raw_ply = raw_move.get("ply", index)
            ply = (
                raw_ply
                if isinstance(raw_ply, int) and not isinstance(raw_ply, bool)
                else index
            )
            provided_san = raw_move.get("san")
        else:
            raise _permanent(f"La jugada {index} no tiene un formato válido.")

        if not isinstance(uci, str) or not uci.strip():
            raise _permanent(f"La jugada {index} no incluye uci.")

        try:
            move = chess.Move.from_uci(uci.strip())
        except ValueError as exc:
            raise _permanent(f"La jugada {index} no es UCI válida.") from exc

        if not board.is_legal(move):
            raise _permanent(f"La jugada {index} no es legal en la posición actual.")

        color = "white" if board.turn == chess.WHITE else "black"
        try:
            san = board.san(move)
        except (ValueError, AssertionError) as exc:
            raise _permanent(f"No se pudo calcular la SAN de la jugada {index}.") from exc

        if not san and isinstance(provided_san, str) and provided_san.strip():
            san = provided_san.strip()

        moves.append(
            GameMove(ply=ply, color=color, uci=uci.strip(), san=san)
        )
        board.push(move)
        positions.append(board.fen())
        terminal_mate.append(board.is_checkmate())

    return GameInput(
        game_id=game_id,
        initial_fen=positions[0],
        moves=tuple(moves),
        positions=tuple(positions),
        terminal_mate=tuple(terminal_mate),
    )


def normalize_evaluation(
    payload: Mapping[str, Any], *, terminal_mate: bool
) -> Evaluation:
    """Convierte la respuesta de Botcito-análisis a centipeones desde blancas."""
    if not isinstance(payload, Mapping):
        raise _permanent("Botcito-análisis devolvió una respuesta inválida.")

    evaluation = payload.get("evaluation")
    if not isinstance(evaluation, Mapping):
        raise _permanent("La respuesta del motor no incluye evaluation.")

    perspective = evaluation.get("perspective")
    if perspective is not None and perspective != "white":
        raise _permanent("La evaluación del motor no está desde blancas.")

    evaluation_type = evaluation.get("type")
    raw_value = evaluation.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise _permanent("La evaluación del motor no tiene un valor entero.")

    if evaluation_type == "mate":
        mate_in = raw_value
        if mate_in > 0:
            value = MATE_SCORE - abs(mate_in)
        elif mate_in < 0:
            value = -(MATE_SCORE - abs(mate_in))
        else:
            value = 0
        is_mate = True
    elif evaluation_type == "cp":
        value = raw_value
        is_mate = terminal_mate or abs(value) >= MATE_SCORE
    else:
        raise _permanent("La evaluación del motor tiene un tipo desconocido.")

    best_uci: str | None = None
    best_san: str | None = None
    best_move = payload.get("bestMove")
    if best_move is not None:
        if not isinstance(best_move, Mapping):
            raise _permanent("El bestMove del motor no tiene un formato válido.")
        raw_uci = best_move.get("uci")
        if not isinstance(raw_uci, str) or not raw_uci.strip():
            raise _permanent("El bestMove del motor no incluye uci.")
        best_uci = raw_uci.strip()
        raw_san = best_move.get("san")
        if isinstance(raw_san, str) and raw_san.strip():
            best_san = raw_san.strip()

    depth = payload.get("depth")
    if isinstance(depth, bool) or not isinstance(depth, int):
        depth = None

    return Evaluation(
        value=value,
        is_mate=is_mate,
        best_uci=best_uci,
        best_san=best_san,
        depth=depth,
    )


def classify(
    *,
    move_uci: str,
    best_uci: str | None,
    cp_loss: int,
    inaccuracy_cp: int,
    mistake_cp: int,
    blunder_cp: int,
) -> str:
    """Clasificación por prioridad (sección 17.4.2)."""
    if best_uci is not None and move_uci.lower() == best_uci.lower():
        return "best"
    if cp_loss >= blunder_cp:
        return "blunder"
    if cp_loss >= mistake_cp:
        return "mistake"
    if cp_loss >= inaccuracy_cp:
        return "inaccuracy"
    return "good"


def compute_result(
    game: GameInput,
    evaluations: tuple[Evaluation, ...] | list[Evaluation],
    *,
    inaccuracy_cp: int,
    mistake_cp: int,
    blunder_cp: int,
) -> dict[str, Any]:
    """Produce ``result: { summary, moves }`` para el documento de análisis."""
    if len(evaluations) != len(game.positions):
        raise _permanent("El número de evaluaciones no coincide con las posiciones.")

    totals: dict[str, dict[str, int]] = {
        "white": {name: 0 for name in CLASSIFICATIONS},
        "black": {name: 0 for name in CLASSIFICATIONS},
    }
    cp_loss_sums = {"white": 0, "black": 0}
    cp_loss_counts = {"white": 0, "black": 0}

    moves: list[dict[str, Any]] = []
    for index, move in enumerate(game.moves):
        before = evaluations[index]
        after = evaluations[index + 1]

        if move.color == "white":
            cp_loss = max(0, before.value - after.value)
        else:
            cp_loss = max(0, after.value - before.value)

        classification = classify(
            move_uci=move.uci,
            best_uci=before.best_uci,
            cp_loss=cp_loss,
            inaccuracy_cp=inaccuracy_cp,
            mistake_cp=mistake_cp,
            blunder_cp=blunder_cp,
        )

        best_move = None
        if before.best_uci is not None:
            best_move = {
                "uci": before.best_uci,
                "san": before.best_san or before.best_uci,
            }

        moves.append(
            {
                "ply": move.ply,
                "color": move.color,
                "uci": move.uci,
                "san": move.san,
                "bestMove": best_move,
                "evalBefore": before.value,
                "evalAfter": after.value,
                "cpLoss": cp_loss,
                "classification": classification,
            }
        )

        totals[move.color][classification] += 1
        if not before.is_mate and not after.is_mate:
            cp_loss_sums[move.color] += cp_loss
            cp_loss_counts[move.color] += 1

    summary: dict[str, dict[str, Any]] = {}
    for color in ("white", "black"):
        side = dict(totals[color])
        count = cp_loss_counts[color]
        side["averageCpLoss"] = (
            round(cp_loss_sums[color] / count, 1) if count else None
        )
        summary[color] = side

    return {"summary": summary, "moves": moves}
