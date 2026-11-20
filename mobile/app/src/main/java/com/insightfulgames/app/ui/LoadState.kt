package com.insightfulgames.app.ui

/** Estados de una pantalla: cargando, error o datos. ("Vacío" lo decide cada pantalla según los datos.) */
sealed interface LoadState<out T> {
    data object Loading : LoadState<Nothing>
    data class Error(val message: String) : LoadState<Nothing>
    data class Success<T>(val data: T) : LoadState<T>
}
