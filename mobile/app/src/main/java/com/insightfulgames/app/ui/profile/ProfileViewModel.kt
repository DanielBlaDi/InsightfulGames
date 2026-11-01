package com.insightfulgames.app.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.ProfileData
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.AuthRepository
import com.insightfulgames.app.data.repository.StatsRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface ProfileUiState {
    data object Loading : ProfileUiState
    data class Error(val message: String) : ProfileUiState
    data class Success(val data: ProfileData) : ProfileUiState
}

class ProfileViewModel(
    private val stats: StatsRepository,
    private val auth: AuthRepository,
) : ViewModel() {

    private val _ui = MutableStateFlow<ProfileUiState>(ProfileUiState.Loading)
    val ui: StateFlow<ProfileUiState> = _ui.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _ui.value = ProfileUiState.Loading
        viewModelScope.launch {
            stats.load()
                .onSuccess { _ui.value = ProfileUiState.Success(it) }
                .onFailure { _ui.value = ProfileUiState.Error(it.userMessage()) }
        }
    }

    fun logout() {
        viewModelScope.launch { auth.logout() }
    }
}
