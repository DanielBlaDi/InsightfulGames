package com.insightfulgames.app.data.remote

import com.insightfulgames.app.data.model.ApiErrorEnvelope
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException
import retrofit2.HttpException
import java.io.IOException

/** Error de API con la forma del contrato. status = 0 si no hubo respuesta HTTP. */
class ApiException(val status: Int, val code: String, message: String) : Exception(message) {
    val isUnauthorized: Boolean get() = status == 401
}

/** Ejecuta una llamada de red y convierte los fallos en [ApiException]. */
suspend fun <T> apiCall(block: suspend () -> T): Result<T> =
    try {
        Result.success(block())
    } catch (e: CancellationException) {
        throw e
    } catch (e: HttpException) {
        Result.failure(e.toApiException())
    } catch (e: IOException) {
        Result.failure(ApiException(0, "NETWORK", "No se pudo conectar con el servidor."))
    } catch (e: SerializationException) {
        Result.failure(ApiException(0, "INVALID_RESPONSE", "El servidor devolvió una respuesta inesperada."))
    }

private fun HttpException.toApiException(): ApiException {
    val raw = runCatching { response()?.errorBody()?.string() }.getOrNull()
    val parsed = raw
        ?.let { runCatching { AppJson.decodeFromString<ApiErrorEnvelope>(it) }.getOrNull() }
        ?.error
    return ApiException(
        status = code(),
        code = parsed?.code ?: "HTTP_${code()}",
        message = parsed?.message ?: "El servidor respondió con el código ${code()}.",
    )
}

/** Mensaje legible para la UI. */
fun Throwable.userMessage(): String {
    if (this !is ApiException) return "Ocurrió un error inesperado."
    return when (code) {
        "INVALID_CREDENTIALS" -> "Usuario o contraseña incorrectos."
        "USERNAME_TAKEN" -> "Ese nombre de usuario ya existe."
        "VALIDATION_ERROR" -> "Revisa los datos: usuario de 3 a 20 caracteres y contraseña de al menos 8 al registrarte."
        "UNAUTHORIZED" -> "Tu sesión expiró. Inicia sesión de nuevo."
        "SERVICES_UNAVAILABLE", "SERVICE_UNAVAILABLE" -> "El servidor no está disponible. Inténtalo más tarde."
        "NETWORK" -> "Sin conexión con el servidor. Revisa tu red."
        "GAME_NOT_FOUND", "MATCH_NOT_FOUND" -> "La partida no existe o ya no es visible."
        else -> message ?: "Ocurrió un error inesperado."
    }
}
