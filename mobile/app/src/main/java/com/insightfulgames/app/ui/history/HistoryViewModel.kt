package com.insightfulgames.app.ui.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.GameSummaryDto
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.GameRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class HistoryUi(
    val items: List<GameSummaryDto> = emptyList(),
    /** null cuando no hay más páginas. */
    val nextCursor: String? = null,
    val initialLoading: Boolean = true,
    val loadingMore: Boolean = false,
    val error: String? = null,
)

/** Historial paginado de a 20; "Cargar más" pide la página siguiente con nextCursor. */
class HistoryViewModel(private val repo: GameRepository) : ViewModel() {

    private val _ui = MutableStateFlow(HistoryUi())
    val ui: StateFlow<HistoryUi> = _ui.asStateFlow()

    init {
        loadFirst()
    }

    fun loadFirst() {
        _ui.value = HistoryUi(initialLoading = true)
        viewModelScope.launch {
            repo.page(cursor = null)
                .onSuccess { page ->
                    _ui.value = HistoryUi(
                        items = page.items,
                        nextCursor = page.nextCursor,
                        initialLoading = false,
                    )
                }
                .onFailure { e ->
                    _ui.value = HistoryUi(initialLoading = false, error = e.userMessage())
                }
        }
    }

    fun loadMore() {
        val current = _ui.value
        val cursor = current.nextCursor ?: return
        if (current.loadingMore || current.initialLoading) return

        _ui.update { it.copy(loadingMore = true, error = null) }
        viewModelScope.launch {
            repo.page(cursor)
                .onSuccess { page ->
                    _ui.update {
                        it.copy(
                            // Por si el servidor repite una partida entre páginas.
                            items = (it.items + page.items).distinctBy { g -> g.gameId },
                            nextCursor = page.nextCursor,
                            loadingMore = false,
                        )
                    }
                }
                .onFailure { e -> _ui.update { it.copy(loadingMore = false, error = e.userMessage()) } }
        }
    }
}
