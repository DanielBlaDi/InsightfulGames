# Insightful Games — App Android

Contratos v9, sección 16. Kotlin · Jetpack Compose · Material 3 · Navigation · Retrofit/OkHttp · kotlinx.serialization · EncryptedSharedPreferences.

Alcance: perfil, estadísticas, historial y detalle. No juega partidas en vivo, no muestra análisis del Tutor y no borra la cuenta.

## Cómo abrirla
1. Android Studio (Koala o más nuevo) → *Open* → esta carpeta.
2. Levantar el **gateway móvil** (puerto 8090) y revisar `BASE_URL` en `app/build.gradle.kts`:
   - Emulador: `http://10.0.2.2:8090/` (ya configurado).
   - Dispositivo físico: `http://<IP-del-PC>:8090/` (mismo Wi-Fi, firewall abierto).
   - Siempre con `/` al final y **sin** `/api`. La app habla con el gateway móvil, no con el web.
3. Sin backend completo: `Backend/api-gateway-mobile/tools/fake_internal_gateway.py` (ver su README).
   Registrarse desde la app crea el usuario en el simulado.

## Pantallas (navegación inferior)
Login/Registro · Inicio (`GET /home`) · Perfil · Estadísticas · Historial (20 por página + "Cargar más") · Detalle.

- Detalle: `local` y `vs_bot` → `GET /games/{gameId}`; `multiplayer` → `GET /matches/{matchId}` (el `matchId` viene en la lista).
- Inicio: una sección en `unavailable` muestra "No disponible en este momento" + Reintentar; el resto se ve normal. No reintenta sola.
- Estados: cargando, datos, vacío, no disponible, sesión expirada.

## Sesión
- Token y usuario cifrados con Android Keystore (`EncryptedSharedPreferences`). Nunca en texto plano.
- 3600 s, sin refresh token. Un 401 en ruta protegida borra la sesión y vuelve al login con aviso.
- Cerrar sesión solo borra el token local (no usa `/auth/logout`).

## Estructura
```
app/src/main/java/com/insightfulgames/app/
├── InsightfulApp.kt     Application + AppContainer (DI manual)
├── data/model           DTOs del contrato (Dtos.kt) y modelos de UI
├── data/local           SessionStore (cifrado)
├── data/remote          ApiService, ApiClient (Bearer + 401), apiCall/ApiException
├── data/repository      Auth, Profile, Game
└── ui                   AppRoot (sesión + navegación), auth/, home/, profile/, stats/, history/, detail/,
                         components/, GameLabels.kt y FenParser.kt (lógica pura con pruebas JUnit)
```

## Pruebas
`./gradlew test` → `GameLabelsTest`, `FenParserTest`.

## Pendiente
- Logo, tipografías (Playfair Display / Plus Jakarta Sans) y modo oscuro.
- Release: poner el dominio HTTPS en `BASE_URL` (el release bloquea HTTP).
