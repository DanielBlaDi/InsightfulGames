"""POST /internal/tutor/analyses: validación, idempotencia y publicación."""

from __future__ import annotations

import uuid

import pytest

from tests.helpers import (
    GAME_1,
    GAME_2,
    USER_A,
    USER_B,
    make_game,
    post_analysis,
)


async def test_crea_analisis_pending_y_publica_evento(tutor):
    tutor.logic.add(make_game())

    response = await post_analysis(tutor)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["gameId"] == GAME_1
    assert body["engineVersion"] == "stockfish-17"
    assert body["depth"] == 15
    assert body["language"] == "es"
    assert body["detailLevel"] == "standard"
    assert uuid.UUID(body["analysisId"])
    assert body["createdAt"].endswith("Z")

    document = await tutor.repository.get(body["analysisId"])
    assert document["status"] == "pending"
    assert document["requestedBy"] == USER_A
    assert document["participantIds"] == [USER_A]
    assert document["visibility"] == "private"
    assert document["result"] is None

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
    assert document["visibility"] == "shared"


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
