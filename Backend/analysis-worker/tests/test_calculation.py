"""Pruebas del cálculo de evaluaciones y de la reconstrucción de posiciones."""

from __future__ import annotations

import pytest

from app.calculation import (
    MATE_SCORE,
    classify,
    compute_result,
    normalize_evaluation,
    parse_game_input,
)
from app.errors import AnalysisFailure
from app.models import Evaluation
from tests.conftest import evaluation_payload, make_game_input, new_uuid


def test_parse_game_input_reconstructs_n_plus_one_positions():
    game_id = new_uuid()
    game = parse_game_input(make_game_input(game_id))

    assert game.game_id == game_id
    assert len(game.positions) == 3
    assert [move.uci for move in game.moves] == ["e2e4", "e7e5"]
    assert [move.color for move in game.moves] == ["white", "black"]
    assert [move.san for move in game.moves] == ["e4", "e5"]
    assert game.terminal_mate == (False, False, False)


def test_parse_game_input_accepts_uci_strings():
    game = parse_game_input(
        make_game_input(new_uuid(), moves=("e2e4", "e7e5"))
        | {"moves": ["e2e4", "e7e5"]}
    )
    assert [move.uci for move in game.moves] == ["e2e4", "e7e5"]


def test_parse_game_input_rejects_invalid_fen():
    with pytest.raises(AnalysisFailure) as captured:
        parse_game_input(
            make_game_input(new_uuid(), initial_fen="not-a-fen", moves=("e2e4",))
        )
    assert captured.value.failure_kind == "permanent"


def test_parse_game_input_rejects_illegal_move():
    with pytest.raises(AnalysisFailure) as captured:
        parse_game_input(make_game_input(new_uuid(), moves=("e2e5",)))
    assert captured.value.failure_kind == "permanent"


def test_parse_game_input_rejects_unfinished_game():
    with pytest.raises(AnalysisFailure):
        parse_game_input(make_game_input(new_uuid(), status="in_progress"))


def test_parse_game_input_rejects_game_id_mismatch():
    with pytest.raises(AnalysisFailure):
        parse_game_input(make_game_input(new_uuid()), expected_game_id=new_uuid())


def test_parse_game_input_rejects_empty_moves():
    with pytest.raises(AnalysisFailure):
        parse_game_input(make_game_input(new_uuid(), moves=()))


@pytest.mark.parametrize(
    ("mate_in", "expected"),
    [
        (3, MATE_SCORE - 3),
        (-2, -(MATE_SCORE - 2)),
        (0, 0),
    ],
)
def test_mate_scores_are_converted_to_centipawns(mate_in, expected):
    evaluation = normalize_evaluation(
        evaluation_payload(mate_in, evaluation_type="mate", best_uci="e2e4"),
        terminal_mate=False,
    )
    assert evaluation.value == expected
    assert evaluation.is_mate is True


def test_terminal_checkmate_marks_evaluation_as_mate():
    evaluation = normalize_evaluation(
        evaluation_payload(MATE_SCORE, best_uci=None), terminal_mate=True
    )
    assert evaluation.value == MATE_SCORE
    assert evaluation.is_mate is True
    assert evaluation.best_uci is None


def test_normalize_evaluation_rejects_black_perspective():
    payload = evaluation_payload(10, best_uci="e2e4")
    payload["evaluation"]["perspective"] = "black"
    with pytest.raises(AnalysisFailure) as captured:
        normalize_evaluation(payload, terminal_mate=False)
    assert captured.value.failure_kind == "permanent"


@pytest.mark.parametrize(
    ("cp_loss", "expected"),
    [
        (49, "good"),
        (50, "inaccuracy"),
        (99, "inaccuracy"),
        (100, "mistake"),
        (299, "mistake"),
        (300, "blunder"),
        (10_000, "blunder"),
    ],
)
def test_classification_thresholds(cp_loss, expected):
    assert (
        classify(
            move_uci="a2a3",
            best_uci="e2e4",
            cp_loss=cp_loss,
            inaccuracy_cp=50,
            mistake_cp=100,
            blunder_cp=300,
        )
        == expected
    )


def test_best_has_priority_over_cp_loss():
    assert (
        classify(
            move_uci="e2e4",
            best_uci="e2e4",
            cp_loss=5000,
            inaccuracy_cp=50,
            mistake_cp=100,
            blunder_cp=300,
        )
        == "best"
    )


def test_compute_result_calculates_cp_loss_and_summary():
    game = parse_game_input(make_game_input(new_uuid()))
    evaluations = [
        Evaluation(100, False, "d2d4", "d4"),
        Evaluation(20, False, "e7e5", "e5"),
        Evaluation(40, False, "g1f3", "Nf3"),
    ]

    result = compute_result(
        game,
        evaluations,
        inaccuracy_cp=50,
        mistake_cp=100,
        blunder_cp=300,
    )

    assert [move["cpLoss"] for move in result["moves"]] == [80, 20]
    assert [move["classification"] for move in result["moves"]] == [
        "inaccuracy",
        "best",
    ]
    assert result["moves"][0]["bestMove"] == {"uci": "d2d4", "san": "d4"}
    assert result["summary"]["white"] == {
        "best": 0,
        "good": 0,
        "inaccuracy": 1,
        "mistake": 0,
        "blunder": 0,
        "averageCpLoss": 80.0,
    }
    assert result["summary"]["black"] == {
        "best": 1,
        "good": 0,
        "inaccuracy": 0,
        "mistake": 0,
        "blunder": 0,
        "averageCpLoss": 20.0,
    }


def test_average_is_null_when_all_moves_are_excluded_by_mate():
    game = parse_game_input(make_game_input(new_uuid(), moves=("e2e4",)))
    evaluations = [
        Evaluation(MATE_SCORE - 3, True, "e2e4", "e4"),
        Evaluation(-(MATE_SCORE - 2), True, "e7e5", "e5"),
    ]

    result = compute_result(
        game,
        evaluations,
        inaccuracy_cp=50,
        mistake_cp=100,
        blunder_cp=300,
    )

    assert result["summary"]["white"]["averageCpLoss"] is None
    assert result["summary"]["black"]["averageCpLoss"] is None


def test_average_rounds_to_one_decimal():
    game = parse_game_input(
        make_game_input(new_uuid(), moves=("e2e4", "e7e5", "g1f3"))
    )
    evaluations = [
        Evaluation(100, False, "d2d4", "d4"),
        Evaluation(90, False, "d7d5", "d5"),
        Evaluation(110, False, "e7e5", "e5"),
        Evaluation(10, False, "b8c6", "Nc6"),
    ]

    result = compute_result(
        game,
        evaluations,
        inaccuracy_cp=50,
        mistake_cp=100,
        blunder_cp=300,
    )

    # Blancas: 10 y 100 -> 55.0; negras: 20 -> 20.0, sin redondeos extraños.
    assert result["summary"]["white"]["averageCpLoss"] == 55.0
    assert result["summary"]["black"]["averageCpLoss"] == 20.0


def test_compute_result_rejects_mismatched_evaluations():
    game = parse_game_input(make_game_input(new_uuid()))
    with pytest.raises(AnalysisFailure) as captured:
        compute_result(
            game,
            [Evaluation(0, False, "e2e4", "e4")],
            inaccuracy_cp=50,
            mistake_cp=100,
            blunder_cp=300,
        )
    assert captured.value.failure_kind == "permanent"
