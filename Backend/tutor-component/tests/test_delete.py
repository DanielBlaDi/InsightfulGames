"""DELETE /internal/tutor/users/{userId}: anonimización y borrado selectivo."""

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


async def _create(tutor, game_id: str, *, user: str) -> str:
    response = await post_analysis(tutor, game_id=game_id, user=user)
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
    assert await tutor.repository.get(privada_compartida) is None

    publica_ajena_doc = await tutor.repository.get(publica_ajena)
    assert publica_ajena_doc is not None
    assert publica_ajena_doc["requestedBy"] == USER_B

    publica_suya_doc = await tutor.repository.get(publica_suya)
    assert publica_suya_doc is not None
    assert publica_suya_doc["requestedBy"] == ANONYMOUS

    assert await tutor.repository.collection.count_documents({}) == 2


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
        {"analysisId": analysis_id}, {"$set": {"requestedBy": ANONYMOUS}}
    )

    response = await tutor.http.delete(f"/internal/tutor/users/{ANONYMOUS}")

    assert response.status_code == 204
    document = await tutor.repository.get(analysis_id)
    assert document is not None
    assert document["requestedBy"] == ANONYMOUS
