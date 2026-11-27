"""Borrado de cuenta: GET /users/{id}/game-ids y POST /users/{id}/erase.

El gateway decide qué se conserva (las partidas shared) consultando Game Logic; el Tutor borra lo
que no esté en keepGameIds y anonimiza el resto, sin llamar a ningún servicio.
"""

from __future__ import annotations

from tests.helpers import (
    ANONYMOUS,
    GAME_1,
    GAME_2,
    GAME_3,
    GAME_4,
    USER_A,
    USER_B,
    make_game,
    post_analysis,
)


async def _create(tutor, game_id: str, *, user: str, user_ids: tuple[str, ...], **payload) -> str:
    response = await post_analysis(
        tutor, game_id=game_id, user=user, game=make_game(game_id, user_ids=user_ids), **payload
    )
    assert response.status_code == 202, response.text
    return response.json()["analysisId"]


async def _erase(tutor, user: str, keep: list[str] | None = None):
    return await tutor.http.post(
        f"/internal/tutor/users/{user}/erase", json={"keepGameIds": keep or []}
    )


# ------------------------------------------------------------------ game-ids


async def test_game_ids_lista_las_partidas_donde_participa(tutor):
    await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))
    await _create(tutor, GAME_2, user=USER_B, user_ids=(USER_A, USER_B))
    await _create(tutor, GAME_3, user=USER_B, user_ids=(USER_B,))

    response = await tutor.http.get(f"/internal/tutor/users/{USER_A}/game-ids")

    assert response.status_code == 200
    assert sorted(response.json()["gameIds"]) == sorted([GAME_1, GAME_2])


async def test_game_ids_de_usuario_sin_analisis_es_lista_vacia(tutor):
    response = await tutor.http.get(f"/internal/tutor/users/{USER_B}/game-ids")

    assert response.status_code == 200
    assert response.json() == {"gameIds": []}


async def test_game_ids_del_valor_anonimo_es_lista_vacia(tutor):
    response = await tutor.http.get(f"/internal/tutor/users/{ANONYMOUS}/game-ids")

    assert response.status_code == 200
    assert response.json() == {"gameIds": []}


async def test_game_ids_con_uuid_invalido_es_validation_error(tutor):
    response = await tutor.http.get("/internal/tutor/users/no-es-un-uuid/game-ids")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------- erase


async def test_borrado_anonimiza_y_elimina_solo_lo_que_no_se_conserva(tutor):
    privada_suya = await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))
    privada_compartida = await _create(tutor, GAME_2, user=USER_B, user_ids=(USER_A, USER_B))
    publica_ajena = await _create(tutor, GAME_3, user=USER_B, user_ids=(USER_B,))
    publica_suya = await _create(tutor, GAME_4, user=USER_A, user_ids=(USER_A,))

    # El gateway decidió conservar solo la partida shared del usuario (GAME_4)
    response = await _erase(tutor, USER_A, keep=[GAME_4])

    assert response.status_code == 204
    assert response.content == b""

    assert await tutor.repository.get(privada_suya) is None
    # Se borran todos los análisis del gameId no conservado, incluso los de otro usuario.
    assert await tutor.repository.get(privada_compartida) is None

    publica_ajena_doc = await tutor.repository.get(publica_ajena)
    assert publica_ajena_doc is not None
    assert publica_ajena_doc["requestedBy"] == USER_B
    assert publica_ajena_doc["participantIds"] == [USER_B]

    publica_suya_doc = await tutor.repository.get(publica_suya)
    assert publica_suya_doc is not None
    assert publica_suya_doc["requestedBy"] == ANONYMOUS
    assert publica_suya_doc["participantIds"] == [ANONYMOUS]
    assert USER_A not in publica_suya_doc["participantIds"]

    assert await tutor.repository.collection.count_documents({}) == 2


async def test_sin_keep_game_ids_se_borra_todo_lo_del_usuario_fail_closed(tutor):
    uno = await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))
    dos = await _create(tutor, GAME_2, user=USER_A, user_ids=(USER_A,))

    response = await _erase(tutor, USER_A, keep=[])

    assert response.status_code == 204
    assert await tutor.repository.get(uno) is None
    assert await tutor.repository.get(dos) is None


async def test_un_keep_de_una_partida_ajena_no_conserva_nada_del_usuario(tutor):
    privada = await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))

    response = await _erase(tutor, USER_A, keep=[GAME_3])

    assert response.status_code == 204
    assert await tutor.repository.get(privada) is None


async def test_anonimiza_participant_ids_de_analisis_pedido_por_otro(tutor):
    analysis_id = await _create(tutor, GAME_1, user=USER_B, user_ids=(USER_A, USER_B))

    response = await _erase(tutor, USER_A, keep=[GAME_1])

    assert response.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document is not None
    assert document["requestedBy"] == USER_B
    assert document["participantIds"] == [ANONYMOUS, USER_B]


async def test_anonimizar_participant_ids_es_idempotente_y_deduplica(tutor):
    analysis_id = await _create(tutor, GAME_1, user=USER_B, user_ids=(USER_A, USER_B))
    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id},
        {"$set": {"participantIds": [ANONYMOUS, USER_A, USER_B]}},
    )

    first = await _erase(tutor, USER_A, keep=[GAME_1])
    second = await _erase(tutor, USER_A, keep=[GAME_1])

    assert first.status_code == 204
    assert second.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document["participantIds"] == [ANONYMOUS, USER_B]


async def test_keep_acepta_uuid_en_mayusculas(tutor):
    analysis_id = await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))

    response = await _erase(tutor, USER_A, keep=[GAME_1.upper()])

    assert response.status_code == 204
    assert await tutor.repository.get(analysis_id) is not None


async def test_keep_game_ids_invalido_es_validation_error_y_no_muta(tutor):
    analysis_id = await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))

    response = await _erase(tutor, USER_A, keep=["no-es-un-uuid"])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    document = await tutor.repository.get(analysis_id)
    assert document is not None and document["requestedBy"] == USER_A


async def test_cuerpo_ausente_es_validation_error(tutor):
    response = await tutor.http.post(f"/internal/tutor/users/{USER_A}/erase")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_borrado_es_idempotente(tutor):
    analysis_id = await _create(tutor, GAME_1, user=USER_A, user_ids=(USER_A,))

    first = await _erase(tutor, USER_A)
    second = await _erase(tutor, USER_A)

    assert first.status_code == 204
    assert second.status_code == 204
    assert await tutor.repository.get(analysis_id) is None


async def test_borrado_de_usuario_sin_analisis_responde_204(tutor):
    response = await _erase(tutor, USER_B)

    assert response.status_code == 204


async def test_borrado_de_usuario_con_uuid_invalido_es_validation_error(tutor):
    response = await tutor.http.post(
        "/internal/tutor/users/no-es-un-uuid/erase", json={"keepGameIds": []}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_borrado_del_valor_anonimo_no_toca_nada(tutor):
    analysis_id = await _create(tutor, GAME_4, user=USER_A, user_ids=(USER_A,))
    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id},
        {"$set": {"requestedBy": ANONYMOUS, "participantIds": [ANONYMOUS]}},
    )

    response = await _erase(tutor, ANONYMOUS)

    assert response.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document is not None
    assert document["requestedBy"] == ANONYMOUS
    assert document["participantIds"] == [ANONYMOUS]


async def test_la_ruta_delete_antigua_ya_no_existe(tutor):
    response = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert response.status_code in (404, 405)
