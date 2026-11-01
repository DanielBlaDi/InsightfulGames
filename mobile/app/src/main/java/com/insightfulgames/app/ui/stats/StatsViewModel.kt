package com.insightfulgames.app.ui.stats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.StatsDto
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.ProfileRepository
import com.insightfulgames.app.ui.LoadState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class StatsViewModel(private val repo: ProfileRepository) : ViewModel() {

    private val _ui = MutableStateFlow<LoadState<StatsDto>>(LoadState.Loading)
    val ui: StateFlow<LoadState<StatsDto>> = _ui.asStateFlow()

    init {
        load()
    }

    fun load() {
        _ui.value = LoadState.Loading
        viewModelScope.launch {
            repo.stats()
                .onSuccess { _ui.value = LoadState.Success(it) }
                .onFailure { _ui.value = LoadState.Error(it.userMessage()) }
        }
    }
}
