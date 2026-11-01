package com.insightfulgames.app.ui.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.HomeDto
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.ProfileRepository
import com.insightfulgames.app.ui.LoadState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class HomeUi(
    val load: LoadState<HomeDto> = LoadState.Loading,
    /** true mientras se reintenta con datos ya en pantalla (el resto de la pantalla no se oculta). */
    val refreshing: Boolean = false,
)

/** La pantalla de inicio no reintenta sola: solo [refresh] (botón Reintentar). */
class HomeViewModel(private val repo: ProfileRepository) : ViewModel() {

    private val _ui = MutableStateFlow(HomeUi())
    val ui: StateFlow<HomeUi> = _ui.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        val current = _ui.value
        if (current.refreshing) return
        val hadData = current.load is LoadState.Success

        _ui.value = if (hadData) current.copy(refreshing = true) else HomeUi(LoadState.Loading)
        viewModelScope.launch {
            repo.home()
                .onSuccess { _ui.value = HomeUi(LoadState.Success(it)) }
                .onFailure { e ->
                    _ui.value = if (hadData) {
                        current.copy(refreshing = false)
                    } else {
                        HomeUi(LoadState.Error(e.userMessage()))
                    }
                }
        }
    }
}
