"""Datos y utilidades compartidas por las pruebas."""

from __future__ import annotations

import httpx

USER_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ANONYMOUS = "00000000-0000-0000-0000-000000000000"

GAME_1 = "11111111-1111-4111-8111-111111111111"
GAME_2 = "22222222-2222-4222-8222-222222222222"
GAME_3 = "33333333-3333-4333-8333-333333333333"
GAME_4 = "44444444-4444-4444-8444-444444444444"

SAMPLE_SUMMARY = {
    "white": {
        "best": 12,
        "good": 8,
        "inaccuracy": 2,
        "mistake": 1,
        "blunder": 0,
        "averageCpLoss": 24,
    },
    "black": {
        "best": 10,
        "good": 9,
        "inaccuracy": 3,
        "mistake": 0,
        "blunder": 1,
        "averageCpLoss": 31,
    },
}

SAMPLE_MOVES = [
    {
        "ply": 1,
        "color": "white",
        "uci": "e2e4",
        "san": "e4",
        "bestMove": {"uci": "e2e4", "san": "e4"},
        "evalBefore": 20,
        "evalAfter": 25,
        "cpLoss": 0,
        "classification": "best",
    }
]

# Jugada mínima del GameState; sirve para que la partida sea analizable.
GAME_MOVES = [
    {
        "ply": 1,
        "color": "white",
        "san": "e4",
        "uci": "e2e4",
        "fenAfter": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        "timestamp": "2026-11-01T15:00:05Z",
    }
]


def make_game(
    game_id: str = GAME_1,
    *,
    status: str = "finished",
    visibility: str = "private",
    user_ids: tuple[str, ...] = (USER_A,),
    mode: str = "multiplayer",
    end_reason: str = "checkmate",
    moves: list | None = None,
    legacy_user_id: str | None = None,
) -> dict:
    colors = ("white", "black", "white", "black")
    game = {
        "gameId": game_id,
        "mode": mode,
        "visibility": visibility,
        "status": status,
        "participants": [
            {"userId": user_id, "color": colors[index]}
            for index, user_id in enumerate(user_ids)
        ],
        "moves": GAME_MOVES if moves is None else moves,
        "result": "white",
        "endReason": end_reason,
    }
    if legacy_user_id is not None:
        game["userId"] = legacy_user_id
    return game


async def post_analysis(
    harness,
    *,
    user: str | None = USER_A,
    game_id: str = GAME_1,
    **payload,
) -> httpx.Response:
    body = {"gameId": game_id, **payload}
    headers = {"X-User-Id": user} if user else {}
    return await harness.http.post(
        "/internal/tutor/analyses", json=body, headers=headers
    )


async def get_status(harness, analysis_id: str, *, user: str | None = USER_A):
    headers = {"X-User-Id": user} if user else {}
    return await harness.http.get(
        f"/internal/tutor/analyses/{analysis_id}", headers=headers
    )


async def get_result(harness, analysis_id: str, *, user: str | None = USER_A):
    headers = {"X-User-Id": user} if user else {}
    return await harness.http.get(
        f"/internal/tutor/analyses/{analysis_id}/result", headers=headers
    )


async def mark_completed(
    harness,
    analysis_id: str,
    *,
    summary: dict | None = None,
    moves: list | None = None,
) -> None:
    await harness.repository.collection.update_one(
        {"analysisId": analysis_id},
        {
            "$set": {
                "status": "completed",
                "result": {
                    "summary": summary or SAMPLE_SUMMARY,
                    "moves": SAMPLE_MOVES if moves is None else moves,
                },
            }
        },
    )


async def mark_failed(
    harness,
    analysis_id: str,
    message: str = "Motor no disponible",
    *,
    failure_kind: str | None = "transient",
    reactivations: int | None = None,
) -> None:
    updates: dict = {
        "status": "failed",
        "error": message,
        "leaseUntil": "2026-11-01T15:10:00Z",
        "leaseOwner": "worker-1",
        "claimCount": 2,
    }
    if failure_kind is not None:
        updates["failureKind"] = failure_kind
    if reactivations is not None:
        updates["reactivations"] = reactivations

    update: dict = {"$set": updates}
    if failure_kind is None:
        update["$unset"] = {"failureKind": ""}
    await harness.repository.collection.update_one(
        {"analysisId": analysis_id}, update
    )
