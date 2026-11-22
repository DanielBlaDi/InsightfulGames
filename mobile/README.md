# Insightful Games — App Android

Contrato técnico definitivo, sección 15 (rutas en 4.11). Kotlin · Jetpack Compose · Material 3 · Navigation · Retrofit/OkHttp · kotlinx.serialization · EncryptedSharedPreferences.

Alcance: perfil, estadísticas, historial, detalle, **partidas locales en vivo** (dos jugadores en el mismo teléfono, con o sin
reloj de 10 min) y **borrado de cuenta**. No juega contra el bot ni multijugador online, y no muestra análisis del Tutor.

## Cómo abrirla
1. Android Studio (Koala o más nuevo) → *Open* → esta carpeta.
2. Levantar el **gateway móvil** (puerto 8090) y revisar `BASE_URL` en `app/build.gradle.kts`:
   - Emulador: `http://10.0.2.2:8090/` (ya configurado).
   - Dispositivo físico: `http://<IP-del-PC>:8090/` (mismo Wi-Fi, firewall abierto).
   - Siempre con `/` al final y **sin** `/api`. La app habla con el gateway móvil, no con el web.
3. **Backend real: validado el 2026-11-21** (MOB-01) en un emulador Android 14 contra `docker compose up` completo
   (app → nginx :8090 → gateway móvil → Auth, Profile/Stats, Game Logic). Funcionó todo esto:
   - registro con login automático, login y validación del formulario;
   - Inicio con perfil, estadísticas y últimas partidas;
   - Historial y el detalle de partidas `local`, `vs_bot` y `multiplayer` (incluida una invitación caducada), con replay;
   - Estadísticas, Perfil y cierre de sesión, que no se restaura al reabrir la app.

   Para eso, Game Logic ahora incluye `matchId`, `endReason` y `color` en cada partida de `GET /games`.
4. Sin backend, o con parte real: `Backend/api-gateway-mobile/README.md` explica cómo correr el gateway móvil contra
   servicios **simulados** o **mixtos** (servicios reales donde existen, simulados donde no). Con el simulado,
   registrarse desde la app crea el usuario en la simulación.

## Pantallas (navegación inferior)
Login/Registro · Inicio (`GET /home`) · Jugar · Perfil · Estadísticas · Historial (20 por página + "Cargar más") · Detalle · Partida.

- Jugar: "Sin reloj" o "10 minutos por bando" → `POST /games` (`mode: local`) → pantalla de partida.
- Partida (`play/{gameId}`): tocar una pieza muestra sus destinos legales (`legalMoves`); cada jugada es `POST /games/{id}/moves`
  con `expectedVersion` (un 409 relee la partida). Coronación con diálogo, girar tablero, rendirse (el color que tiene el turno)
  y relojes que corren en pantalla; al llegar a 0 la app relee la partida hasta que el backend la cierra por tiempo.
  La lógica de entrada (`ui/play/MoveInput.kt`) es pura y tiene pruebas JUnit.
- Una partida local `in_progress` del historial muestra "Continuar partida" en el detalle.
- Perfil → "Borrar cuenta": hay que escribir el nombre de usuario. `DELETE /auth/account` (hasta 70 s de espera); si sale bien
  se borra la sesión y el login muestra "Tu cuenta fue borrada"; si falla (503) se muestra el error y se puede reintentar.

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
`FenParserTest`, `ReplayTest` y `MoveInputTest` (selección, destinos, coronación y relojes).

El wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`) se copió de `Backend/GameLogic/`; el `.jar` se
versiona gracias a la excepción de `mobile/.gitignore`. `gradle-wrapper.properties` fija Gradle 8.9. Si `./gradlew --version`
falla, regenera con `gradle wrapper --gradle-version 8.9` (o desde Android Studio).

## Probar en un emulador (sin Android Studio)
Ejemplo con el SDK y los AVD en `D:\Android` (PowerShell):
```powershell
$env:ANDROID_SDK_ROOT = "D:\Android\Sdk"; $env:ANDROID_AVD_HOME = "D:\Android\avd"
D:\Android\Sdk\emulator\emulator.exe -avd insightful34 -no-snapshot
.\gradlew.bat assembleDebug
D:\Android\Sdk\platform-tools\adb.exe install -r app\build\outputs\apk\debug\app-debug.apk
```
El emulador necesita la aceleración WHPX (Windows Hypervisor Platform); compruébala con `emulator -accel-check`.

## Pendiente
- Logo, tipografías (Playfair Display / Plus Jakarta Sans) y modo oscuro.
- Release: poner el dominio HTTPS en `BASE_URL` (el release bloquea HTTP).