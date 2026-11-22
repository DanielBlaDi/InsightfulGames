package com.insightfulgames.app.data.remote

import com.insightfulgames.app.BuildConfig
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

val AppJson = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
}

object ApiClient {
    private const val ACCOUNT_DELETION_TIMEOUT_S = 70

    /**
     * @param tokenProvider token vigente (o null).
     * @param onUnauthorized se llama con el token usado cuando una ruta protegida responde 401.
     */
    fun create(
        baseUrl: String,
        tokenProvider: () -> String?,
        onUnauthorized: (tokenUsed: String?) -> Unit,
    ): ApiService {
        val authInterceptor = Interceptor { chain ->
            val token = tokenProvider()
            val request = chain.request().newBuilder().apply {
                if (token != null) header("Authorization", "Bearer $token")
            }.build()

            // El borrado de cuenta es una saga que puede tardar hasta 60 s en el gateway (nginx espera 65 s).
            val isAccountDeletion = request.method == "DELETE" && request.url.encodedPath.endsWith("/auth/account")
            val response = if (isAccountDeletion) {
                chain.withReadTimeout(ACCOUNT_DELETION_TIMEOUT_S, TimeUnit.SECONDS).proceed(request)
            } else {
                chain.proceed(request)
            }

            // 401 en login/registro = credenciales incorrectas: no cierra nada.
            val path = request.url.encodedPath
            val isAuthRoute = path.endsWith("/auth/login") || path.endsWith("/auth/register")
            if (response.code == 401 && !isAuthRoute) {
                onUnauthorized(token)
            }
            response
        }

        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .addInterceptor(authInterceptor)
            .apply {
                if (BuildConfig.DEBUG) {
                    // BASIC: método, URL y código. Nunca cabeceras ni cuerpos (token, contraseña).
                    addInterceptor(
                        HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC },
                    )
                }
            }
            .build()

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(AppJson.asConverterFactory("application/json; charset=UTF-8".toMediaType()))
            .build()
            .create(ApiService::class.java)
    }
}
