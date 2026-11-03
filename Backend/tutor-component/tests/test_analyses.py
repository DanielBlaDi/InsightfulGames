"""POST /internal/tutor/analyses: validación, idempotencia y publicación."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.models import is_retryable
from tests.helpers import (
    GAME_1,
    GAME_2,
    USER_A,
    USER_B,
    get_status,
    make_game,
    mark_failed,
    post_analysis,
)


async def test_crea_analisis_pending_y_publica_evento(tutor):
    tutor.logic.add(make_game())

    response = await post_analysis(tutor)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["gameId"] == GAME_1
    assert body["engineVersion"] == "stockfish-15.1"
    assert body["depth"] == 15
    assert body["language"] == "es"
    assert body["detailLevel"] == "standard"
    assert body["retryable"] is False
    assert uuid.UUID(body["analysisId"])
    assert body["createdAt"].endswith("Z")

    document = await tutor.repository.get(body["analysisId"])
    assert document["status"] == "pending"
    assert document["requestedBy"] == USER_A
    assert document["participantIds"] == [USER_A]
    assert document["reactivations"] == 0
    assert document["error"] is None
    assert document["explanation"] is None
    # El Tutor no escribe campos del worker ni una copia de la visibilidad.
    assert "visibility" not in document
    assert "result" not in document
    assert "startedAt" not in document
    assert "completedAt" not in document

    assert len(tutor.publisher.published) == 1
    event = tutor.publisher.published[0]
    assert event["analysisId"] == body["analysisId"]
    assert event["gameId"] == GAME_1
    assert event["requestedBy"] == USER_A
    assert event["depth"] == 15
    assert event["language"] == "es"
    assert event["detailLevel"] == "standard"


async def test_segunda_peticion_igual_devuelve_200_sin_republicar(tutor):
    tutor.logic.add(make_game())

    first = await post_analysis(tutor)
    second = await post_analysis(tutor)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["analysisId"] == first.json()["analysisId"]
    assert len(tutor.publisher.published) == 1
    assert await tutor.repository.collection.count_documents({}) == 1


async def test_depth_por_defecto_y_explicita_forman_claves_distintas(tutor):
    tutor.logic.add(make_game())

    default = await post_analysis(tutor)
    sharper = await post_analysis(tutor, depth=18)
    shallower = await post_analysis(tutor, depth=10)

    assert len(
        {
            default.json()["analysisId"],
            sharper.json()["analysisId"],
            shallower.json()["analysisId"],
        }
    ) == 3
    assert sharper.status_code == 202
    assert shallower.json()["depth"] == 10
    assert await tutor.repository.collection.count_documents({}) == 3


async def test_language_y_detail_level_forman_parte_de_la_clave(tutor):
    tutor.logic.add(make_game())

    first = await post_analysis(tutor, language="es", detailLevel="standard")
    english = await post_analysis(tutor, language="en")
    detailed = await post_analysis(tutor, detailLevel="detailed")

    ids = {
        first.json()["analysisId"],
        english.json()["analysisId"],
        detailed.json()["analysisId"],
    }
    assert len(ids) == 3


async def test_duplicado_simultaneo_devuelve_el_existente(tutor, monkeypatch):
    tutor.logic.add(make_game())
    first = await post_analysis(tutor)

    original = tutor.repository.find_by_key
    calls = {"n": 0}

    async def find_by_key_que_falla_la_primera_vez(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # simula que la comprobación previa no vio nada
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        tutor.repository, "find_by_key", find_by_key_que_falla_la_primera_vez
    )

    second = await post_analysis(tutor)

    assert second.status_code == 200
    assert second.json()["analysisId"] == first.json()["analysisId"]
    assert await tutor.repository.collection.count_documents({}) == 1
    assert len(tutor.publisher.published) == 1


@pytest.mark.parametrize("depth", [0, 19, 100, -1])
async def test_depth_fuera_de_rango_es_validation_error(tutor, depth):
    tutor.logic.add(make_game())

    response = await post_analysis(tutor, depth=depth)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_depth_no_entero_es_validation_error(tutor):
    tutor.logic.add(make_game())

    response = await post_analysis(tutor, depth="quince")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_game_id_invalido_es_validation_error(tutor):
    response = await post_analysis(tutor, game_id="no-es-un-uuid")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_sin_x_user_id_es_unauthorized(tutor):
    tutor.logic.add(make_game())

    response = await post_analysis(tutor, user=None)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_x_user_id_invalido_es_unauthorized(tutor):
    tutor.logic.add(make_game())

    response = await tutor.http.post(
        "/internal/tutor/analyses",
        json={"gameId": GAME_1},
        headers={"X-User-Id": "invalido"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


async def test_partida_inexistente_es_game_not_found(tutor):
    response = await post_analysis(tutor)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GAME_NOT_FOUND"
    assert await tutor.repository.collection.count_documents({}) == 0


async def test_partida_en_curso_es_game_not_finished(tutor):
    tutor.logic.add(make_game(status="in_progress"))

    response = await post_analysis(tutor)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GAME_NOT_FINISHED"
    assert await tutor.repository.collection.count_documents({}) == 0


async def test_partida_expirada_es_game_not_analyzable(tutor):
    tutor.logic.add(make_game(end_reason="expired"))

    response = await post_analysis(tutor)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GAME_NOT_ANALYZABLE"
    assert await tutor.repository.collection.count_documents({}) == 0


async def test_partida_sin_jugadas_es_game_not_analyzable(tutor):
    tutor.logic.add(make_game(moves=[]))

    response = await post_analysis(tutor)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GAME_NOT_ANALYZABLE"
    assert await tutor.repository.collection.count_documents({}) == 0
    assert tutor.publisher.published == []


async def test_partida_privada_de_otro_usuario_no_es_visible(tutor):
    tutor.logic.add(make_game(user_ids=(USER_A, USER_B)))

    response = await post_analysis(tutor, user=USER_B)
    another = await post_analysis(tutor, user="cccccccc-cccc-4ccc-8ccc-cccccccccccc")

    assert response.status_code == 202
    assert another.status_code == 404
    assert another.json()["error"]["code"] == "GAME_NOT_FOUND"


async def test_partida_shared_la_puede_pedir_cualquiera(tutor):
    tutor.logic.add(make_game(visibility="shared", user_ids=(USER_A,)))

    response = await post_analysis(tutor, user=USER_B)

    assert response.status_code == 202
    document = await tutor.repository.get(response.json()["analysisId"])
    assert "visibility" not in document
    assert document["participantIds"] == [USER_A]


async def test_game_state_sin_visibility_no_es_visible_ni_usa_user_id(tutor):
    game = {
        "gameId": GAME_1,
        "userId": USER_A,
        "createdBy": USER_A,
        "mode": "local",
        "status": "finished",
        "participants": [{"userId": USER_A, "color": "white"}],
        "moves": [{"ply": 1, "color": "white", "san": "e4", "uci": "e2e4"}],
        "result": "white",
        "endReason": "checkmate",
    }
    tutor.logic.add(game)

    response = await post_analysis(tutor, user=USER_A)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GAME_NOT_FOUND"
    assert await tutor.repository.collection.count_documents({}) == 0


async def test_game_logic_caido_devuelve_503(tutor):
    tutor.logic.down = True

    response = await post_analysis(tutor)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


async def test_fallo_de_publicacion_deja_el_analisis_pending(tutor):
    tutor.logic.add(make_game())
    tutor.publisher.accepting = False

    response = await post_analysis(tutor)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    document = await tutor.repository.get(body["analysisId"])
    assert document["status"] == "pending"
    assert tutor.publisher.published == []


async def test_acepta_id_uuid_en_mayusculas_y_lo_normaliza(tutor):
    tutor.logic.add(make_game(game_id=GAME_2))

    response = await post_analysis(tutor, game_id=GAME_2.upper())

    assert response.status_code == 202
    assert response.json()["gameId"] == GAME_2


# ---------------------------------------------------------------- Reactivación


async def _failed_analysis(tutor, **failed_kwargs) -> str:
    tutor.logic.add(make_game())
    created = await post_analysis(tutor)
    assert created.status_code == 202
    analysis_id = created.json()["analysisId"]
    await mark_failed(tutor, analysis_id, **failed_kwargs)
    return analysis_id


async def test_fallo_transitorio_se_reactiva_con_202(tutor):
    analysis_id = await _failed_analysis(tutor, reactivations=0)
    published_before = len(tutor.publisher.published)

    response = await post_analysis(tutor)

    assert response.status_code == 202
    body = response.json()
    assert body["analysisId"] == analysis_id
    assert body["status"] == "pending"
    assert body["retryable"] is False
    assert body["error"] is None

    document = await tutor.repository.get(analysis_id)
    assert document["status"] == "pending"
    assert document["reactivations"] == 1
    assert document["error"] is None
    assert document["requestedBy"] == USER_A
    assert "failureKind" not in document
    assert "leaseUntil" not in document
    assert "leaseOwner" not in document
    assert "claimCount" not in document

    assert len(tutor.publisher.published) == published_before + 1
    assert tutor.publisher.published[-1]["analysisId"] == analysis_id
    assert tutor.publisher.published[-1]["requestedBy"] == USER_A


async def test_fallo_permanente_responde_200_sin_republicar(tutor):
    analysis_id = await _failed_analysis(tutor, failure_kind="permanent")
    published_before = len(tutor.publisher.published)

    response = await post_analysis(tutor)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["retryable"] is False
    assert body["analysisId"] == analysis_id
    assert len(tutor.publisher.published) == published_before
    document = await tutor.repository.get(analysis_id)
    assert document["status"] == "failed"
    assert document["reactivations"] == 0


async def test_fallo_sin_failure_kind_no_se_reactiva(tutor):
    analysis_id = await _failed_analysis(tutor, failure_kind=None)
    published_before = len(tutor.publisher.published)

    response = await post_analysis(tutor)

    assert response.status_code == 200
    assert response.json()["retryable"] is False
    assert len(tutor.publisher.published) == published_before
    document = await tutor.repository.get(analysis_id)
    assert document["status"] == "failed"


async def test_maximo_de_reactivaciones_alcanzado_no_reactiva(tutor):
    analysis_id = await _failed_analysis(tutor, reactivations=3)
    published_before = len(tutor.publisher.published)

    response = await post_analysis(tutor)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["retryable"] is False
    assert len(tutor.publisher.published) == published_before
    document = await tutor.repository.get(analysis_id)
    assert document["reactivations"] == 3


async def test_dos_post_simultaneos_reactivan_una_sola_vez(tutor):
    analysis_id = await _failed_analysis(tutor, reactivations=0)
    published_before = len(tutor.publisher.published)

    responses = await asyncio.gather(
        post_analysis(tutor), post_analysis(tutor)
    )

    assert sorted(response.status_code for response in responses) == [200, 202]
    assert len(tutor.publisher.published) == published_before + 1
    document = await tutor.repository.get(analysis_id)
    assert document["reactivations"] == 1
    assert document["status"] == "pending"


def test_retryable_solo_aplica_a_fallos_transitorios():
    transient = {
        "status": "failed",
        "failureKind": "transient",
        "reactivations": 2,
    }
    assert is_retryable(transient, 3) is True
    assert is_retryable({**transient, "reactivations": 3}, 3) is False
    assert is_retryable({**transient, "failureKind": "permanent"}, 3) is False
    assert is_retryable({**transient, "status": "pending"}, 3) is False
    assert is_retryable(transient, 0) is False
