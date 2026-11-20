# Insightful Games — App Android

Contrato técnico definitivo, sección 15 (rutas en 4.11). Kotlin · Jetpack Compose · Material 3 · Navigation · Retrofit/OkHttp · kotlinx.serialization · EncryptedSharedPreferences.

Alcance: perfil, estadísticas, historial y detalle. No juega partidas en vivo, no muestra análisis del Tutor y no borra la cuenta.

## Cómo abrirla
1. Android Studio (Koala o más nuevo) → *Open* → esta carpeta.
2. Levantar el **gateway móvil** (puerto 8090) y revisar `BASE_URL` en `app/build.gradle.kts`:
   - Emulador: `http://10.0.2.2:8090/` (ya configurado).
   - Dispositivo físico: `http://<IP-del-PC>:8090/` (mismo Wi-Fi, firewall abierto).
   - Siempre con `/` al final y **sin** `/api`. La app habla con el gateway móvil, no con el web.
3. **Backend real: todavía NO validado.** Esta app se probó solo contra simuladores. Para llegar a los servicios reales
   falta el passthrough `/internal/*` del gateway web (GW-04); además Game Logic aún no entrega la lista en el formato del
   contrato (GL-04), Single Player no tiene rutas internas (SP-05) y Multiplayer no existe. Este README se actualizará con lo
   que se compruebe en emulador (MOB-01).
4. Sin backend, o con parte real: `Backend/api-gateway-mobile/README.md` explica cómo correr el gateway móvil contra
   un gateway interno **simulado** o **mixto** (servicios reales donde existen, simulados donde no). Con el simulado,
   registrarse desde la app crea el usuario en la simulación.

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
Desde `mobile/` (necesita JDK 17 y el Android SDK; define `ANDROID_HOME` o `sdk.dir` en `local.properties`):
```bash
./gradlew test          # Windows: gradlew.bat test
```
Cubre `GameLabelsTest` (incluye la etiqueta de `account_deleted`), `UserMessageTest` (`PROFILE_NOT_FOUND` es "no disponible"),
`FenParserTest` y `ReplayTest`.

El wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`) se copió de `Backend/GameLogic/`; el `.jar` se
versiona gracias a la excepción de `mobile/.gitignore`. `gradle-wrapper.properties` fija Gradle 8.9. Si `./gradlew --version`
falla, regenera con `gradle wrapper --gradle-version 8.9` (o desde Android Studio).

## Pendiente
- Logo, tipografías (Playfair Display / Plus Jakarta Sans) y modo oscuro.
- Release: poner el dominio HTTPS en `BASE_URL` (el release bloquea HTTP).