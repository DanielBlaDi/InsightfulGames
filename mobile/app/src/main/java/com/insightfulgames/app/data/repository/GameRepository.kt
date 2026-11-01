package com.insightfulgames.app.data.repository

import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.model.GamesPageDto
import com.insightfulgames.app.data.remote.ApiService
import com.insightfulgames.app.data.remote.apiCall

class GameRepository(private val api: ApiService) {

    /** Una página de 20 partidas (todos los modos), de la más reciente a la más antigua. */
    suspend fun page(cursor: String? = null): Result<GamesPageDto> =
        apiCall { api.games(limit = PAGE_SIZE, cursor = cursor) }

    suspend fun detail(kind: DetailKind, id: String): Result<GameStateDto> = apiCall {
        when (kind) {
            DetailKind.GAME -> api.game(id)
            DetailKind.MATCH -> api.match(id)
        }
    }

    companion object {
        const val PAGE_SIZE = 20
    }
}
