package com.insightfulgames.app.data.remote

import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import com.insightfulgames.app.data.model.ApiErrorEnvelope
import retrofit2.HttpException
import java.io.IOException

/** Error de API con la forma uniforme del contrato. status = 0 si ni siquiera hubo respuesta HTTP. */
class ApiException(val status: Int, val code: String, message: String) : Exception(message)

private val errorJson = Json { ignoreUnknownKeys = true }

/** Ejecuta una llamada de red y devuelve Result, convirtiendo los fallos en ApiException. */
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
    val parsed = raw?.let { runCatching { errorJson.decodeFromString<ApiErrorEnvelope>(it) }.getOrNull() }?.error
    return ApiException(
        status = code(),
        code = parsed?.code ?: "HTTP_${code()}",
        message = parsed?.message ?: "El servidor respondió con el código ${code()}.",
    )
}

/** Mensaje legible para mostrar en la UI. */
fun Throwable.userMessage(): String =
    if (this is ApiException) {
        when (code) {
            "INVALID_CREDENTIALS" -> "Usuario o contraseña incorrectos."
            "VALIDATION_ERROR" -> "Revisa el usuario y la contraseña."
            "SERVICE_UNAVAILABLE" -> "El servidor no está disponible. Inténtalo más tarde."
            else -> message ?: "Ocurrió un error inesperado."
        }
    } else {
        "Ocurrió un error inesperado."
    }
