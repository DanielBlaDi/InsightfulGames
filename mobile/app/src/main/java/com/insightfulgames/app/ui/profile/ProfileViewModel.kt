package com.insightfulgames.app.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.model.ProfileDto
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.AuthRepository
import com.insightfulgames.app.data.repository.ProfileRepository
import com.insightfulgames.app.ui.LoadState
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** Borrado de cuenta: Idle, Deleting o Error (con el mensaje del servidor; la sesión sigue abierta). */
sealed interface DeleteState {
    data object Idle : DeleteState
    data object Deleting : DeleteState
    data class Error(val message: String) : DeleteState
}

class ProfileViewModel(
    private val repo: ProfileRepository,
    private val auth: AuthRepository,
) : ViewModel() {

    private val _ui = MutableStateFlow<LoadState<ProfileDto>>(LoadState.Loading)
    val ui: StateFlow<LoadState<ProfileDto>> = _ui.asStateFlow()

    init {
        load()
    }

    fun load() {
        _ui.value = LoadState.Loading
        viewModelScope.launch {
            repo.profile()
                .onSuccess { _ui.value = LoadState.Success(it) }
                .onFailure { _ui.value = LoadState.Error(it.userMessage()) }
        }
    }

    fun logout() {
        viewModelScope.launch { auth.logout() }
    }

    private val _delete = MutableStateFlow<DeleteState>(DeleteState.Idle)
    val delete: StateFlow<DeleteState> = _delete.asStateFlow()

    /** Si sale bien, la sesión se cierra y AppRoot vuelve al login con el aviso de cuenta borrada. */
    fun deleteAccount() {
        if (_delete.value == DeleteState.Deleting) return
        _delete.value = DeleteState.Deleting
        viewModelScope.launch {
            auth.deleteAccount()
                .onSuccess { _delete.value = DeleteState.Idle }
                .onFailure { _delete.value = DeleteState.Error(it.userMessage()) }
        }
    }

    fun resetDelete() {
        if (_delete.value != DeleteState.Deleting) _delete.value = DeleteState.Idle
    }
}
