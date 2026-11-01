package com.insightfulgames.app.data.remote

import com.insightfulgames.app.BuildConfig
import com.insightfulgames.app.data.local.SessionStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {

    fun create(
        baseUrl: String,
        sessionStore: SessionStore,
        onUnauthorized: () -> Unit,
    ): ApiService {
        val json = Json { ignoreUnknownKeys = true }

        // Añade "Authorization: Bearer <token>" y, ante un 401 en rutas protegidas
        // (token vencido o inválido), avisa para cerrar la sesión. El 401 del propio
        // login (credenciales incorrectas) no cierra nada.
        val authInterceptor = Interceptor { chain ->
            // Se ejecuta en un hilo de OkHttp, no en el principal.
            val token = runBlocking { sessionStore.session.first()?.token }
            val request = chain.request().newBuilder().apply {
                if (token != null) header("Authorization", "Bearer $token")
            }.build()

            val response = chain.proceed(request)
            if (response.code == 401 && !request.url.encodedPath.endsWith("/auth/login")) {
                onUnauthorized()
            }
            response
        }

        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .addInterceptor(authInterceptor)
            .apply {
                if (BuildConfig.DEBUG) {
                    // BASIC: solo método, URL y código; nunca cabeceras ni cuerpos (token, contraseña).
                    addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC })
                }
            }
            .build()

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json; charset=UTF-8".toMediaType()))
            .build()
            .create(ApiService::class.java)
    }
}
