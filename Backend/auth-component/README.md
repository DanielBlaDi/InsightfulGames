# Auth Component — InsightfulGames

## 1. Descripción

`auth-component` es el componente de autenticación de InsightfulGames. Está desarrollado con Java 21 y Spring Boot y utiliza una base de datos relacional MySQL para almacenar los usuarios.

Sus responsabilidades son:

- Registrar usuarios.
- Autenticar usuarios mediante nombre de usuario y contraseña.
- Almacenar contraseñas mediante hash BCrypt, nunca en texto plano.
- Generar tokens JWT firmados con HS256.
- Eliminar cuentas de usuario.
- Exponer un endpoint de salud para comprobar la disponibilidad del servicio.

## 2. Tecnologías

- Java 21
- Spring Boot
- Maven
- Spring Data JPA
- Spring Security
- MySQL 8.4
- JWT (HS256)
- Docker y Docker Compose

## 3. Ubicación

```text
InsightfulGames/
├── Backend/
│   └── auth-component/
│       ├── src/
│       ├── pom.xml
│       ├── Dockerfile
│       └── README.md
├── databases/
│   └── auth/
│       ├── 01-init.sql
│       └── README.md
├── compose.yaml
├── .env
└── .env.example
```

## 4. Configuración del entorno

Las variables de entorno se configuran en el archivo `.env`, ubicado en la raíz del repositorio, junto a `compose.yaml`.

Variables necesarias:

```env
MYSQL_DATABASE=auth
MYSQL_USER=usuario_de_aplicacion
MYSQL_PASSWORD=contraseña_de_aplicacion
MYSQL_ROOT_PASSWORD=contraseña_root
JWT_SECRET=secreto_criptografico
```

Utiliza valores propios y secretos seguros. El archivo `.env` no debe subirse a Git; únicamente debe compartirse `.env.example` con valores de ejemplo no confidenciales.

Para generar un secreto JWT en PowerShell:

```powershell
[Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLower()
```

Copia el resultado en `JWT_SECRET`. Genera secretos diferentes para cada entorno.

## 5. Ejecución con Docker Compose

Desde la raíz de `InsightfulGames`, con Docker Desktop en ejecución:

```powershell
docker compose up --build -d
```

Consultar el estado:

```powershell
docker compose ps
```

Consultar los logs de autenticación:

```powershell
docker compose logs --tail=100 auth-component
```

Consultar los logs de la base de datos:

```powershell
docker compose logs --tail=100 mysql-component
```

Detener los servicios:

```powershell
docker compose down
```

Para detenerlos sin eliminar los datos de MySQL, no utilices `docker compose down -v`.

**Nota sobre compatibilidad:** durante las pruebas de desarrollo se detectó el error `Fatal glibc error: CPU does not support x86-64-v2` con la imagen `mysql:8.4` en el equipo utilizado. Hasta resolver esa incompatibilidad, no se puede garantizar que el despliegue completo funcione en ese equipo. El motor previsto para el proyecto sigue siendo MySQL.

## 6. Ejecución local de Spring Boot

También es posible ejecutar la aplicación fuera de Docker, desde la carpeta del componente:

```powershell
cd Backend/auth-component
mvn spring-boot:run
```

Esta modalidad requiere:

- Java 21 y Maven disponibles.
- Una instancia de MySQL accesible.
- Una base de datos `auth` inicializada con el esquema requerido.
- Las variables de entorno de conexión y `JWT_SECRET` configuradas.

Si ejecutas Spring Boot localmente, la URL JDBC debe apuntar a la dirección accesible desde Windows; el nombre `mysql-component` de Docker Compose solo se resuelve dentro de la red de Compose.

## 7. Endpoints de la API

La dirección local prevista es `http://localhost:8081`.

| Método | Endpoint | Descripción | Respuesta exitosa |
|---|---|---|---|
| GET | `/health` | Comprueba el estado del servicio | `200 OK` |
| POST | `/auth/register` | Registra un usuario | `201 Created` |
| POST | `/auth/login` | Inicia sesión | `200 OK` |
| DELETE | `/auth/account` | Elimina una cuenta | `204 No Content` |

### 7.1. Health check

```powershell
curl.exe -i "http://localhost:8081/health"
```

Respuesta esperada:

```json
{
  "status": "ok"
}
```

### 7.2. Registro de usuario

```powershell
curl.exe -i -X POST "http://localhost:8081/auth/register" `
  -H "Content-Type: application/json" `
  --data-raw '{"username":"ana","password":"MiClave123"}'
```

Respuesta esperada: `201 Created`.

```json
{
  "userId": "uuid-del-usuario",
  "username": "ana"
}
```

Reglas previstas:

- `username`: entre 3 y 20 caracteres.
- `password`: mínimo 8 caracteres.
- Cada usuario debe tener un nombre de usuario único.

Errores previstos:

- `400 Bad Request`: datos inválidos.
- `409 Conflict`: nombre de usuario ya registrado.

### 7.3. Inicio de sesión

Utiliza las mismas credenciales del registro:

```powershell
curl.exe -i -X POST "http://localhost:8081/auth/login" `
  -H "Content-Type: application/json" `
  --data-raw '{"username":"ana","password":"MiClave123"}'
```

Respuesta esperada: `200 OK`.

```json
{
  "accessToken": "jwt-generado-por-la-aplicacion",
  "expiresIn": 3600,
  "user": {
    "userId": "uuid-del-usuario",
    "username": "ana"
  }
}
```

El token JWT contiene la identidad del usuario en `sub`, el nombre de usuario y las fechas de emisión y expiración. Su duración prevista es de 3600 segundos.

Error previsto:

- `401 Unauthorized`: credenciales incorrectas.

### 7.4. Eliminación de cuenta

El contrato actual utiliza la cabecera `X-User-Id`. Debes reemplazar el UUID del ejemplo por el `userId` obtenido durante el registro.

```powershell
curl.exe -i -X DELETE "http://localhost:8081/auth/account" `
  -H "X-User-Id: UUID-REAL-DEL-USUARIO"
```

Respuesta esperada: `204 No Content`, sin cuerpo de respuesta.

Errores previstos:

- `400 Bad Request`: falta el identificador requerido.
- `404 Not Found`: el usuario no existe.

**Importante para integración:** `X-User-Id` no debe considerarse una prueba de identidad por sí solo. Cuando se integre con el API Gateway, este debe validar el JWT, extraer el `sub` verificado, establecer la cabecera y eliminar cualquier valor que el cliente haya enviado previamente. El endpoint de eliminación no debe quedar expuesto públicamente sin esa protección.

## 8. Integración con el API Gateway

El API Gateway debe conocer:

- Servicio interno: `auth-component`.
- Puerto interno: `8081`.
- Endpoints públicos de registro e inicio de sesión.
- Formato JSON UTF-8.
- Token JWT en la cabecera `Authorization: Bearer <jwt>` para las rutas protegidas que correspondan.
- Identificador del usuario en el claim `sub`.

La emisión de un JWT no implica automáticamente que Spring Security esté validando tokens en todas las solicitudes. Antes de utilizar el servicio en un entorno compartido o de producción, se debe verificar la configuración del filtro JWT y la protección de las rutas privadas.

## 9. Verificación rápida

Después de iniciar los servicios:

1. Consultar `GET /health`.
2. Registrar un usuario nuevo.
3. Iniciar sesión con las mismas credenciales.
4. Comprobar que se recibe un JWT.
5. Eliminar la cuenta usando el UUID obtenido.
6. Comprobar en la base de datos que la cuenta ya no existe.

Si una operación falla, consultar primero los logs de `auth-component` y `mysql-component` para distinguir errores de aplicación, conexión y esquema.