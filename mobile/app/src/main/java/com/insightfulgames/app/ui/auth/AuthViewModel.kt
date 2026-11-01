package com.insightfulgames.app.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.insightfulgames.app.data.remote.userMessage
import com.insightfulgames.app.data.repository.AuthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AuthUiState(
    val username: String = "",
    val password: String = "",
    val registerMode: Boolean = false,
    val loading: Boolean = false,
    val error: String? = null,
)

class AuthViewModel(private val auth: AuthRepository) : ViewModel() {

    private val _ui = MutableStateFlow(AuthUiState())
    val ui: StateFlow<AuthUiState> = _ui.asStateFlow()

    /** true si la sesión anterior se cerró por un 401 (token vencido). */
    val sessionExpired: StateFlow<Boolean> = auth.sessionExpired

    fun onUsernameChange(value: String) = _ui.update { it.copy(username = value, error = null) }
    fun onPasswordChange(value: String) = _ui.update { it.copy(password = value, error = null) }
    fun toggleMode() = _ui.update { it.copy(registerMode = !it.registerMode, error = null) }

    fun submit() {
        val current = _ui.value
        if (current.loading) return

        val username = current.username.trim()
        // Mismas reglas que Auth: usuario de 3 a 20; contraseña de 8 o más al registrarse.
        val error = when {
            username.length !in 3..20 -> "El usuario debe tener entre 3 y 20 caracteres."
            current.registerMode && current.password.length < 8 ->
                "La contraseña debe tener al menos 8 caracteres."
            current.password.isEmpty() -> "Introduce tu contraseña."
            else -> null
        }
        if (error != null) {
            _ui.update { it.copy(error = error) }
            return
        }

        _ui.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            val result = if (current.registerMode) {
                auth.register(username, current.password)
            } else {
                auth.login(username, current.password)
            }
            result
                .onSuccess {
                    // La sesión guardada hace que AppRoot cambie a la app.
                    // Se limpia el formulario para no dejar la contraseña en memoria.
                    _ui.value = AuthUiState()
                }
                .onFailure { e -> _ui.update { it.copy(loading = false, error = e.userMessage()) } }
        }
    }
}
