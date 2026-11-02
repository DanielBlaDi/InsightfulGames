package com.insightfulgames.app.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.DetailKind
import com.insightfulgames.app.data.model.GameStateDto
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.GameRepository
import com.insightfulgames.app.ui.LoadState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class DetailViewModel(
    private val kind: DetailKind,
    private val id: String,
    private val repo: GameRepository,
) : ViewModel() {

    private val _ui = MutableStateFlow<LoadState<GameStateDto>>(LoadState.Loading)
    val ui: StateFlow<LoadState<GameStateDto>> = _ui.asStateFlow()

    init {
        load()
    }

    fun load() {
        _ui.value = LoadState.Loading
        viewModelScope.launch {
            repo.detail(kind, id)
                .onSuccess { _ui.value = LoadState.Success(it) }
                .onFailure { _ui.value = LoadState.Error(it.userMessage()) }
        }
    }
}
