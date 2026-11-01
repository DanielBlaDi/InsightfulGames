package com.insightfulgames.app.ui.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.AuthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    val loading: Boolean = false,
    val error: String? = null,
)

class LoginViewModel(private val auth: AuthRepository) : ViewModel() {

    private val _ui = MutableStateFlow(LoginUiState())
    val ui: StateFlow<LoginUiState> = _ui.asStateFlow()

    fun onUsernameChange(value: String) = _ui.update { it.copy(username = value, error = null) }
    fun onPasswordChange(value: String) = _ui.update { it.copy(password = value, error = null) }

    fun submit() {
        val current = _ui.value
        if (current.loading) return

        val username = current.username.trim()
        // Mismas reglas que el gateway: usuario de 3 a 20 caracteres, contraseña obligatoria.
        if (username.length !in 3..20 || current.password.isEmpty()) {
            _ui.update { it.copy(error = "Introduce tu usuario (3 a 20 caracteres) y tu contraseña.") }
            return
        }

        _ui.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            auth.login(username, current.password)
                .onSuccess {
                    // La sesión guardada hace que AppRoot cambie al perfil.
                    // Se limpia el formulario para que no quede la contraseña en memoria.
                    _ui.value = LoginUiState()
                }
                .onFailure { e ->
                    _ui.update { it.copy(loading = false, error = e.userMessage()) }
                }
        }
    }
}
