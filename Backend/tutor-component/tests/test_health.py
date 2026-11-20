"""Salud del servicio, índices y visibilidad fail-closed."""

from __future__ import annotations

from pymongo.errors import ServerSelectionTimeoutError

from tests.helpers import GAME_1, USER_A, make_game, post_analysis


async def test_health_ok(tutor):
    response = await tutor.http.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_falla_si_falta_el_indice_unico(tutor):
    await tutor.repository.collection.drop_index("uq_analyses_key")

    response = await tutor.http.get("/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


async def test_los_indices_incluyen_participant_ids(tutor):
    indexes = await tutor.repository.collection.index_information()

    assert indexes["uq_analyses_key"]["unique"] is True
    assert indexes["ix_analyses_participant_ids"]["key"] == [("participantIds", 1)]


async def test_health_falla_si_mongo_no_responde(tutor, monkeypatch):
    async def unhealthy():
        return False

    monkeypatch.setattr(tutor.repository, "healthy", unhealthy)

    response = await tutor.http.get("/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


async def test_mongo_caido_devuelve_503_en_la_api(tutor, monkeypatch):
    tutor.logic.add(make_game(GAME_1, user_ids=(USER_A,)))

    async def boom(*_args, **_kwargs):
        raise ServerSelectionTimeoutError("sin conexión a Mongo")

    monkeypatch.setattr(tutor.repository, "find_by_key", boom)

    response = await post_analysis(tutor)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICES_UNAVAILABLE"


async def test_openapi_se_genera_sin_errores(tutor):
    response = await tutor.http.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/internal/tutor/analyses" in paths
    assert "/internal/tutor/analyses/{analysis_id}/result" in paths
    assert "/internal/tutor/users/{user_id}" in paths


async def test_local_del_creador_es_visible_aunque_repita_user_id(tutor):
    game = make_game(user_ids=(USER_A, USER_A), mode="local")
    tutor.logic.add(game)

    response = await post_analysis(tutor, user=USER_A)

    assert response.status_code == 202
    document = await tutor.repository.get(response.json()["analysisId"])
    assert document["participantIds"] == [USER_A]
