El componente auth-component administra el registro de usuarios, la autenticación, la emisión de tokens JWT y la eliminación de cuentas.

Está desarrollado con Java 21 y Spring Boot. Utiliza MySQL para persistir los usuarios y BCrypt para almacenar las contraseñas de forma segura.

Responsabilidad del componente: validar las credenciales y emitir tokens JWT.


2. Tecnologías

Java 21

Spring Boot

Spring Web

Spring Data JPA

Spring Security

MySQL 8.4

BCrypt

JWT con algoritmo HS256

Docker Compose

3. Endpoints disponibles

La dirección base durante el desarrollo es http://localhost:8081.

GET /health

Verifica el estado del servicio.

Respuesta 200 OK:

{
  "status": "ok"
}

POST /auth/register

Registra un usuario nuevo.

Solicitud:

{
  "username": "ana",
  "password": "miClaveSegura123"
}

Respuesta 201 Created:

{
  "userId": "uuid-del-usuario",
  "username": "ana"
}

Reglas de validación:

username: entre 3 y 20 caracteres.

password: mínimo 8 caracteres.

El nombre de usuario debe ser único.

Errores esperados:

400 Bad Request: VALIDATION_ERROR.

409 Conflict: USERNAME_TAKEN.

POST /auth/login

Autentica a un usuario y genera un JWT.

Solicitud:

{
  "username": "ana",
  "password": "miClaveSegura123"
}

Respuesta 200 OK:

{
  "accessToken": "jwt-generado",
  "expiresIn": 3600,
  "user": {
    "userId": "uuid-del-usuario",
    "username": "ana"
  }
}

Error esperado:

401 Unauthorized: INVALID_CREDENTIALS.

El token tiene una duración de 3600 segundos (1 hora).

DELETE /auth/account

Elimina la cuenta del usuario autenticado.

Cabecera esperada:

X-User-Id: uuid-del-usuario

Respuesta:

204 No Content: cuenta eliminada.

400 Bad Request: VALIDATION_ERROR, si falta o es inválido el identificador.

404 Not Found: USER_NOT_FOUND, si el usuario no existe.

Importante: el Gateway debe eliminar cualquier cabecera X-User-Id proporcionada por el cliente y establecerla únicamente después de validar el JWT. El servicio Auth no debe confiar en una cabecera enviada directamente por un cliente.

4. Integración con el Gateway

El flujo recomendado es:

El cliente envía sus credenciales a POST /auth/login.

El Gateway reenvía la solicitud al componente Auth.

Auth verifica las credenciales y devuelve el JWT.

El cliente incluye el token en las solicitudes protegidas:

Authorization: Bearer <accessToken>

El Gateway valida la firma, el algoritmo y la fecha de expiración del token.

Si el token es válido, el Gateway obtiene el identificador del usuario del claim sub.

El Gateway elimina cualquier X-User-Id recibido del cliente y establece esa cabecera con el valor verificado.

El Gateway reenvía la solicitud al servicio interno correspondiente.

Claims del JWT

Claim

Contenido

sub

Identificador UUID del usuario

username

Nombre de usuario

iat

Fecha de emisión

exp

Fecha de expiración

El algoritmo de firma es HS256.

El Gateway debe utilizar el mismo secreto configurado mediante JWT_SECRET para validar la firma. Ese secreto debe compartirse de forma segura entre los servicios que lo necesiten; nunca debe incluirse en el repositorio ni entregarse al cliente.

5. Configuración

Variables utilizadas por Auth:

Variable

Propósito

SERVER_PORT

Puerto HTTP; por defecto, 8081

SPRING_DATASOURCE_URL

URL JDBC de MySQL

SPRING_DATASOURCE_USERNAME

Usuario de MySQL

SPRING_DATASOURCE_PASSWORD

Contraseña de MySQL

JWT_SECRET

Secreto de firma JWT, de al menos 32 bytes

En Docker Compose, el servicio de base de datos se identifica como mysql-component, y la base de datos de Auth se llama auth.

No se debe subir el archivo .env al repositorio. Las credenciales reales y el secreto JWT deben configurarse de forma segura en cada entorno.

6. Base de datos

La base de datos auth contiene la tabla users:

Columna

Propósito

user_id

Identificador UUID del usuario

username

Nombre de usuario único

password_hash

Hash BCrypt de la contraseña

El script inicial está ubicado en databases/auth/01-init.sql.

Hibernate está configurado con ddl-auto: validate: valida el esquema existente, pero no debe utilizarse como sustituto de los scripts de creación de la base de datos.

7. Ejecución local con Docker Compose

Desde la raíz del repositorio:

Crear el archivo .env usando .env.example como referencia.

Configurar contraseñas y generar un JWT_SECRET aleatorio de al menos 32 bytes.

Iniciar los servicios:

docker compose up --build -d

Consultar los registros:

docker compose logs -f auth-component

Verificar el estado:

curl http://localhost:8081/health

Para detener los servicios:

docker compose down

El volumen de MySQL conserva los datos. El script 01-init.sql se ejecuta automáticamente cuando MySQL inicializa un volumen vacío; modificar ese script posteriormente no actualiza una base de datos que ya esté inicializada.

8. Consideraciones de seguridad

Nunca almacenar contraseñas en texto plano.

No registrar contraseñas ni tokens completos en los logs.

No confiar en cabeceras de identidad enviadas directamente por los clientes.

No exponer el puerto interno de Auth públicamente en producción.

Mantener JWT_SECRET fuera del control de versiones.

Restringir el acceso a Auth a los componentes autorizados de la arquitectura.

Antes de producción, verificar que las rutas internas no queden accesibles sin pasar por los controles del Gateway.

9. Estado de implementación

Los contratos y archivos de configuración descritos documentan la implementación prevista. Antes de considerar el componente listo para integrarse, se deben verificar la compilación, la conexión con MySQL, el registro, el inicio de sesión, la validación del JWT y la eliminación de cuentas.

La validación de JWT y el control de acceso a las rutas de negocio corresponden al Gateway.