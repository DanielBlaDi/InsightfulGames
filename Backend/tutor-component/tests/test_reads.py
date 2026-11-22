"""GET estado, resultado y game-ref: estados y explicación (la visibilidad la comprueba el gateway)."""

from __future__ import annotations

from tests.helpers import (
    GAME_1,
    GAME_2,
    SAMPLE_MOVES,
    SAMPLE_SUMMARY,
    USER_A,
    get_result,
    get_status,
    make_game,
    mark_completed,
    mark_failed,
    post_analysis,
)


async def _create(tutor, *, user=USER_A, **kwargs) -> str:
    response = await post_analysis(tutor, user=user, **kwargs)
    assert response.status_code == 202
    return response.json()["analysisId"]


async def test_estado_pending(tutor):
    analysis_id = await _create(tutor)

    response = await get_status(tutor, analysis_id)

    assert response.status_code == 200
    body = response.json()
    assert body["analysisId"] == analysis_id
    assert body["status"] == "pending"
    assert body["depth"] == 15


async def test_estado_processing_y_failed(tutor):
    analysis_id = await _create(tutor)

    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id}, {"$set": {"status": "processing"}}
    )
    processing = await get_status(tutor, analysis_id)
    assert processing.json()["status"] == "processing"

    await mark_failed(tutor, analysis_id, "El motor no respondió")
    failed = await get_status(tutor, analysis_id)
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["error"] == "El motor no respondió"
    assert failed.json()["retryable"] is True


async def test_analisis_inexistente_es_analysis_not_found(tutor):
    response = await get_status(tutor, "99999999-9999-4999-8999-999999999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


async def test_id_invalido_tambien_es_analysis_not_found(tutor):
    response = await get_status(tutor, "no-es-un-uuid")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"










async def test_resultado_antes_de_completed_es_analysis_not_ready(tutor):
    analysis_id = await _create(tutor)

    response = await get_result(tutor, analysis_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"


async def test_resultado_completed_incluye_informe_y_genera_explicacion(tutor):
    analysis_id = await _create(tutor)

    document = await tutor.repository.get(analysis_id)
    assert document["explanation"] is None

    await mark_completed(tutor, analysis_id, summary=SAMPLE_SUMMARY, moves=SAMPLE_MOVES)

    response = await get_result(tutor, analysis_id)

    assert response.status_code == 200
    body = response.json()
    assert body["analysisId"] == analysis_id
    assert body["gameId"] == GAME_1
    assert body["engineVersion"] == "stockfish-15.1"
    assert body["depth"] == 15
    assert body["language"] == "es"
    assert body["detailLevel"] == "standard"
    assert body["summary"] == SAMPLE_SUMMARY
    assert body["moves"] == SAMPLE_MOVES
    assert body["createdAt"].endswith("Z")
    assert "Blancas" in body["explanation"]
    assert "Negras" in body["explanation"]
    assert "24" in body["explanation"] and "31" in body["explanation"]
    assert "blancas" in body["explanation"]

    stored = await tutor.repository.get(analysis_id)
    assert stored["explanation"] == body["explanation"]

    again = await get_result(tutor, analysis_id)
    assert again.status_code == 200
    assert again.json()["explanation"] == body["explanation"]


async def test_resultado_tolera_summary_y_moves_en_la_raiz(tutor):
    analysis_id = await _create(tutor)

    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id},
        {
            "$set": {
                "status": "completed",
                "summary": SAMPLE_SUMMARY,
                "moves": SAMPLE_MOVES,
            }
        },
    )

    response = await get_result(tutor, analysis_id)

    assert response.status_code == 200
    assert response.json()["summary"] == SAMPLE_SUMMARY
    assert response.json()["moves"] == SAMPLE_MOVES


async def test_completed_sin_resultado_no_entrega_informe(tutor):
    analysis_id = await _create(tutor)
    await tutor.repository.collection.update_one(
        {"analysisId": analysis_id}, {"$set": {"status": "completed"}}
    )

    response = await get_result(tutor, analysis_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_READY"


async def test_explicacion_en_ingles(tutor):
    analysis_id = await _create(tutor, language="en")
    await mark_completed(tutor, analysis_id)

    response = await get_result(tutor, analysis_id)

    assert response.status_code == 200
    assert "White" in response.json()["explanation"]
    assert "Average loss per move" in response.json()["explanation"]


async def test_promedio_nulo_se_muestra_como_no_disponible(tutor):
    analysis_id = await _create(tutor)
    summary = {
        "white": {**SAMPLE_SUMMARY["white"], "averageCpLoss": None},
        "black": {**SAMPLE_SUMMARY["black"], "averageCpLoss": None},
    }
    await mark_completed(tutor, analysis_id, summary=summary)

    response = await get_result(tutor, analysis_id)

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert "no disponible" in explanation
    assert "0 cp" not in explanation
    assert "más preciso" not in explanation


async def test_explicacion_brief_y_detailed(tutor):
    brief_id = await _create(tutor, detailLevel="brief")
    await mark_completed(tutor, brief_id)
    brief = (await get_result(tutor, brief_id)).json()["explanation"]

    detailed_id = await _create(tutor, game_id=GAME_2, detailLevel="detailed")
    await mark_completed(tutor, detailed_id)
    detailed = (await get_result(tutor, detailed_id)).json()["explanation"]

    assert "Pérdida media" not in brief
    assert "Pérdida media" in detailed
    assert "50 centipeones" in detailed
    assert brief != detailed


async def test_game_ref_devuelve_la_partida_del_analisis(tutor):
    analysis_id = await _create(tutor)

    response = await tutor.http.get(f"/internal/tutor/analyses/{analysis_id}/game-ref")

    assert response.status_code == 200
    assert response.json() == {"gameId": GAME_1}


async def test_game_ref_de_analisis_inexistente_es_analysis_not_found(tutor):
    response = await tutor.http.get(
        "/internal/tutor/analyses/99999999-9999-4999-8999-999999999999/game-ref"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


async def test_las_lecturas_no_exigen_x_user_id(tutor):
    # La identidad ya no interviene en las lecturas: el gateway comprobó la visibilidad antes
    analysis_id = await _create(tutor)
    await mark_completed(tutor, analysis_id)

    assert (await get_status(tutor, analysis_id)).status_code == 200
    assert (await get_result(tutor, analysis_id)).status_code == 200
