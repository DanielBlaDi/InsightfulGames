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

