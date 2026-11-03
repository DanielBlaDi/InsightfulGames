"""DELETE /internal/tutor/users/{userId}: borrado por visibilidad actual."""

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


async def _create(tutor, game_id: str, *, user: str, **payload) -> str:
    response = await post_analysis(tutor, game_id=game_id, user=user, **payload)
    assert response.status_code == 202, response.text
    return response.json()["analysisId"]


async def test_borrado_anonimiza_y_elimina_solo_lo_privado(tutor):
    tutor.logic.add(make_game(GAME_1, visibility="private", user_ids=(USER_A,)))
    tutor.logic.add(make_game(GAME_2, visibility="private", user_ids=(USER_A, USER_B)))
    tutor.logic.add(make_game(GAME_3, visibility="shared", user_ids=(USER_B,)))
    tutor.logic.add(make_game(GAME_4, visibility="shared", user_ids=(USER_A,)))

    privada_suya = await _create(tutor, GAME_1, user=USER_A)
    privada_compartida = await _create(tutor, GAME_2, user=USER_B)
    publica_ajena = await _create(tutor, GAME_3, user=USER_B)
    publica_suya = await _create(tutor, GAME_4, user=USER_A)

    response = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert response.status_code == 204
    assert response.content == b""

    assert await tutor.repository.get(privada_suya) is None
    # Se borran todos los análisis del gameId privado, incluso los de otro usuario.
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


async def test_borrado_usa_la_visibilidad_actual(tutor):
    tutor.logic.add(make_game(GAME_1, visibility="private", user_ids=(USER_A,)))
    tutor.logic.add(make_game(GAME_2, visibility="shared", user_ids=(USER_A,)))
    ahora_publica = await _create(tutor, GAME_1, user=USER_A)
    ahora_privada = await _create(tutor, GAME_2, user=USER_A)

    # Sin cambiar los documentos: la partida cambió de visibilidad después.
    tutor.logic.add(make_game(GAME_1, visibility="shared", user_ids=(USER_A,)))
    tutor.logic.add(make_game(GAME_2, visibility="private", user_ids=(USER_A,)))

    response = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert response.status_code == 204
    conservado = await tutor.repository.get(ahora_publica)
    assert conservado is not None
    assert conservado["requestedBy"] == ANONYMOUS
    assert conservado["participantIds"] == [ANONYMOUS]
    assert await tutor.repository.get(ahora_privada) is None


async def test_anonimiza_participant_ids_de_analisis_pedido_por_otro(tutor):
    tutor.logic.add(
        make_game(GAME_1, visibility="shared", user_ids=(USER_A, USER_B))
    )
    analysis_id = await _create(tutor, GAME_1, user=USER_B)

    response = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert response.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document is not None
    assert document["requestedBy"] == USER_B
    assert document["participantIds"] == [ANONYMOUS, USER_B]


async def test_anonimizar_participant_ids_es_idempotente_y_deduplica(tutor):
    tutor.logic.add(
        make_game(GAME_1, visibility="shared", user_ids=(USER_A, USER_B))
    )
    analysis_id = await _create(tutor, GAME_1, user=USER_B)
    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id},
        {"$set": {"participantIds": [ANONYMOUS, USER_A, USER_B]}},
    )

    first = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")
    second = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert first.status_code == 204
    assert second.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document["participantIds"] == [ANONYMOUS, USER_B]


async def test_fallo_de_game_logic_no_muta_ningun_analisis(tutor):
    tutor.logic.add(make_game(GAME_1, visibility="private", user_ids=(USER_A,)))
    tutor.logic.add(make_game(GAME_2, visibility="private", user_ids=(USER_A,)))
    primero = await _create(tutor, GAME_1, user=USER_A)
    segundo = await _create(tutor, GAME_2, user=USER_A)

    tutor.logic.failing_ids.add(GAME_2)

    response = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"

    # La resolución es de dos fases: GAME_1 se pudo leer, pero no se tocó.
    for analysis_id in (primero, segundo):
        document = await tutor.repository.get(analysis_id)
        assert document is not None
        assert document["requestedBy"] == USER_A
        assert document["participantIds"] == [USER_A]


async def test_partida_inexistente_borra_sus_analisis(tutor):
    tutor.logic.add(make_game(GAME_1, visibility="shared", user_ids=(USER_A,)))
    analysis_id = await _create(tutor, GAME_1, user=USER_A)
    tutor.logic.remove(GAME_1)

    response = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert response.status_code == 204
    assert await tutor.repository.get(analysis_id) is None


async def test_borrado_es_idempotente(tutor):
    tutor.logic.add(make_game(GAME_1, visibility="private", user_ids=(USER_A,)))
    analysis_id = await _create(tutor, GAME_1, user=USER_A)

    first = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")
    second = await tutor.http.delete(f"/internal/tutor/users/{USER_A}")

    assert first.status_code == 204
    assert second.status_code == 204
    assert await tutor.repository.get(analysis_id) is None


async def test_borrado_de_usuario_sin_analisis_responde_204(tutor):
    response = await tutor.http.delete(f"/internal/tutor/users/{USER_B}")

    assert response.status_code == 204


async def test_borrado_de_usuario_con_uuid_invalido_es_validation_error(tutor):
    response = await tutor.http.delete("/internal/tutor/users/no-es-un-uuid")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_borrado_del_valor_anonimo_no_toca_nada(tutor):
    tutor.logic.add(make_game(GAME_4, visibility="shared", user_ids=(USER_A,)))
    analysis_id = await _create(tutor, GAME_4, user=USER_A)
    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id},
        {
            "$set": {
                "requestedBy": ANONYMOUS,
                "participantIds": [ANONYMOUS],
            }
        },
    )

    response = await tutor.http.delete(f"/internal/tutor/users/{ANONYMOUS}")

    assert response.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document is not None
    assert document["requestedBy"] == ANONYMOUS
    assert document["participantIds"] == [ANONYMOUS]
