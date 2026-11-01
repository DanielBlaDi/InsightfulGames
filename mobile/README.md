# Insightful Games — App Android (esqueleto)

Login + perfil con estadísticas (partidas jugadas, terminadas, en curso, por modo y récord contra el bot).
Kotlin · Jetpack Compose · Material 3 · Retrofit/OkHttp · kotlinx.serialization · DataStore.

## Cómo abrirla
1. Android Studio (Koala o más nuevo) → *Open* → esta carpeta. El sync descarga Gradle 8.9 y las dependencias.
2. Levantar el backend (`docker compose up`) y revisar `BASE_URL` en `app/build.gradle.kts`:
   - Emulador: `http://10.0.2.2:8080/` (ya configurado; 8080 = `API_GATEWAY_PORT`).
   - Dispositivo físico: `http://<IP-del-PC>:<API_GATEWAY_PORT>/` (mismo Wi-Fi, firewall abierto).
   - Siempre con "/" al final y sin el prefijo `/api` (ese solo existe en el nginx del frontend web).
3. Ejecutar. Probar con un usuario creado en la web (`POST /auth/register`).

## Estructura
```
app/src/main/java/com/insightfulgames/app/
├── InsightfulApp.kt          Application + AppContainer (DI manual)
├── MainActivity.kt
├── data/
│   ├── model/                DTOs del contrato y modelos de dominio
│   ├── remote/               ApiService (Retrofit), ApiClient (OkHttp + Bearer + 401), apiCall/ApiException
│   ├── local/SessionStore    token + usuario en DataStore
│   └── repository/           AuthRepository, StatsRepository
└── ui/
    ├── AppRoot.kt            sesión guardada => Perfil; sin sesión => Login
    ├── login/                LoginScreen + LoginViewModel
    ├── profile/              ProfileScreen + ProfileViewModel
    └── theme/                paleta "Terracotta & Tallow"
```

## Contrato con el backend

**Ya existe y la app lo usa**
- `POST /auth/login` → `{ accessToken, expiresIn, user{userId, username} }`
- `GET /games` (Bearer) → `[{ gameId, mode, status, result, createdAt }]`
- Errores: `{ "error": { "code", "message" } }`; un 401 en rutas protegidas cierra la sesión.

**Falta en el backend** (la app funciona sin esto, pero sin victorias/derrotas):

Opción A — endpoint nuevo `GET /users/me/stats` (Gateway → Single Player → Game Logic, con agregación en Mongo):
```json
{
  "totalGames": 12, "finished": 10, "inProgress": 2,
  "byMode": { "local": 4, "vs_bot": 8 },
  "vsBot": { "wins": 5, "losses": 2, "draws": 1 }
}
```
(No usar `/games/stats`: choca con `GET /games/{game_id}` del gateway.)

Opción B — ampliar `GameSummary` con `playerColor`, `botLevel`, `endReason`, `finishedAt`.
La app ya calcula el récord sola desde `GET /games` en cuanto llega `playerColor`.

`StatsRepository` prueba A y, si el gateway da 404, cae a B.

## Pendiente / TODO
- Cifrar el token con Android Keystore (hoy va en DataStore, almacenamiento privado de la app).
- Sin refresh token: a la hora el token vence y la app vuelve al login.
- Logo, tipografías (Playfair Display / Plus Jakarta Sans) y modo oscuro.
- Registro de usuarios (`POST /auth/register` ya existe).
- Tests unitarios de `StatsRepository` (cálculo de récord).
- Release: poner el dominio HTTPS en `BASE_URL`; el release bloquea HTTP.
