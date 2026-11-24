# InsightfulGames
This is a web-based platform where users can learn and play chess, Go, and Shogi. Initially focused on chess, it offers single-player and multiplayer modes and an AI-powered tutor that analyzes moves, explains mistakes, and provides personalized guidance to help players improve.

The project uses a container-oriented architecture with a frontend, an API gateway, backend services, and databases. Docker Compose provides a unified way to build, configure, and run the application.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation and Setup](#installation-and-setup)
- [Running the Application](#running-the-application)
- [Accessing the Application](#accessing-the-application)
- [Verifying the Services](#verifying-the-services)
- [Stopping the Application](#stopping-the-application)


## Prerequisites

Install the following software before proceeding:

- [Git](https://git-scm.com/downloads) — to clone the repository.
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine — to build and run containers.
- **Docker Compose v2** — available as `docker compose` in supported Docker installations.

Verify the installation:

```bash
git --version
docker --version
docker compose version
```

Make sure Docker is running before starting the application.

The host must also have sufficient resources for the configured services and any required ports available.

## Installation and Setup

### 1. Clone the repository

Clone the repository and switch to the `main` branch:

```bash
git clone --branch main https://github.com/DanielBlaDi/InsightfulGames.git
cd InsightfulGames
```

### 2. Configure environment variables

Create the local environment file from the provided template:

```bash
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

Review `.env.example` and configure the required values in `.env` according to the project's configuration.

Environment variables may include database credentials, service configuration, secrets, and application settings.

Use the variable names and expected values defined by the project. Do not invent missing variables or commit real credentials to Git.

### **Important:** The application may not start correctly if required variables are missing or incorrectly configured.

### 3. Check the Docker Compose configuration

From the repository root, validate the Compose configuration:

```bash
docker compose config --quiet
```

If validation fails, review the error message and check the `.env` configuration before proceeding.

This command validates the resolved Compose configuration; it does not start the application.

## Running the Application

### 1. Build and start the services

From the directory containing `compose.yaml`, run:

```bash
docker compose up --build -d
```

This command builds the images defined by the Compose configuration when necessary and starts the services in detached mode.

The first startup may take several minutes, depending on the number of services, image downloads, and database initialization tasks.

### 2. Check the container status

Run:

```bash
docker compose ps
```

Review the status of the configured services and check whether any containers have exited or are restarting.

### 3. Inspect the logs

To follow the logs from all services:

```bash
docker compose logs -f
```

To inspect the most recent log entries:

```bash
docker compose logs --tail=100
```

Press `Ctrl+C` to stop following the logs. This does not stop the containers.

If a service fails to start, inspect its logs and resolve the reported configuration or startup error.

## Accessing the Application

Once the frontend container is running and its dependencies are ready, open the following address in your browser:

**Frontend:** http://localhost:80

The application should display the Insightful Games interface.

Use the available authentication flow to access the platform. If demonstration accounts are provided by the project, use the credentials documented in the corresponding configuration or demonstration instructions.

Do not assume that particular usernames or passwords are available unless they have been explicitly provided by the project.

If the frontend does not load, check the container status, frontend logs, and port mapping in `compose.yaml`.

## Verifying the Services

Use the following commands to inspect the running application:

| Command | Purpose |
|---|---|
| `docker compose ps` | Lists the Compose services and their container status. |
| `docker compose logs -f` | Follows logs from all services. |
| `docker compose logs --tail=100` | Shows the most recent log entries. |
| `docker compose config --quiet` | Validates the resolved Compose configuration. |

The expected result is that the required containers are running without persistent startup errors.

A running container does not necessarily mean that its application is ready to accept requests. Check the logs if a service is still initializing or cannot connect to its dependencies.

## Stopping the Application

To stop the application and remove its Compose-managed containers and networks, run:

```bash
docker compose down
```

Named volumes are retained by default, so database data stored in those volumes is normally preserved.

To start the application again, use:

```bash
docker compose up -d
```

If you have changed the application code or its Docker build configuration and need to rebuild the images, use:

```bash
docker compose up --build -d
```

**Warning:** Avoid `docker compose down -v` unless you intentionally want to remove the Compose-managed named volumes as well. This can permanently delete locally persisted database data.

## Mobile app (Android)

The Android app lives in `mobile/` and reaches the mobile gateway through the mobile WAF and reverse proxy.

1. Configure `.env` and the TLS certificates as described in `docs/secure-channel-tls.md` (section 11.4).
2. Run `docker compose up -d --build`.
3. Check `https://localhost:<MOBILE_HTTPS_PORT>/health`.
4. Open `mobile/` in Android Studio. Configure the emulator to use `https://10.0.2.2:<MOBILE_HTTPS_PORT>/` and trust the development CA. See `mobile/README.md`.

Profile and statistics come from the Profile/Stats service. Right after registering, the profile appears once the `user.registered` event is consumed (about a second); until then the app shows "No disponible en este momento" with a retry button.

Tests: `cd Backend/api-gateway-mobile && pip install -r requirements-dev.txt && pytest -q` and `cd Backend/api-gateway && pip install -r requirements-dev.txt && pytest -q`.


## Seguridad perimetral: WAF Web y Mobile + Secure Channel

InsightfulGames utiliza dos WAF independientes basados en OWASP ModSecurity CRS. Cada WAF termina TLS para
poder inspeccionar las peticiones y abre una nueva conexión HTTPS, con certificado y nombre verificados, hacia
su reverse proxy.

Arquitectura Web:
Navegador -> HTTPS/WSS -> WAF Web (8443; 8080 solo redirige a HTTPS) -> HTTPS -> Reverse Proxy Web -> Frontend / API Gateway Web

Arquitectura Mobile:
Android -> HTTPS -> WAF Mobile (8444; sin HTTP) -> HTTPS -> Reverse Proxy Mobile -> API Gateway Mobile

Los puertos son los de `.env` (`FRONTEND_PORT`, `FRONTEND_HTTPS_PORT`, `MOBILE_HTTPS_PORT`). Del reverse proxy
hacia los gateways el tráfico sigue en HTTP dentro de las redes privadas.

### Iniciar el proyecto con los WAF

Antes, crea los certificados (público de desarrollo e internos) y las variables de `.env` según
`docs/secure-channel-tls.md` (sección 11.4). Después, desde la raíz del repositorio:

    docker compose up --build -d

Los WAF y los reverse proxies comparten `public_network` (`10.20.1.0/24`). Solo los WAF publican puertos en el host.

### Controles de seguridad

- ModSecurity con OWASP Core Rule Set activado (paranoia y umbrales por defecto).
- Bloqueo de patrones SQL Injection y XSS.
- Métodos permitidos: web `GET HEAD POST OPTIONS PATCH DELETE`; móvil `GET HEAD POST OPTIONS DELETE`.
- TLS 1.2/1.3 del cliente al WAF y del WAF al reverse proxy (CA interna y nombre verificados).
- Certificados público e interno separados, montados en solo lectura y fuera de Git.
- WAF y reverse proxies independientes para Web y Mobile.
- Protección de rutas internas, `X-User-Id` filtrado y rate limiting en los reverse proxies.
- Soporte WebSocket seguro (WSS) en el canal Web.

### Archivos relacionados

- compose.yaml
- Backend/waf/real-ip.conf
- Backend/reverse-proxy/nginx/
- Backend/reverse-proxy/secure-channel/ (certificados internos, validación y verificación)
- docs/secure-channel-tls.md
