"""Conexión a MongoDB de análisis.

Cada componente es dueño de sus datos (contrato, sección 18): el Tutor es dueño
del esquema y el Analysis Worker solo actualiza status, result y error.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# Si Mongo no responde, las peticiones fallan rápido con 503 en lugar de
# quedarse colgadas hasta el timeout del gateway.
SERVER_SELECTION_TIMEOUT_MS = 3000


def create_mongo_client(url: str) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(
        url,
        tz_aware=True,
        serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
        uuidRepresentation="standard",
    )


def get_database(client: AsyncIOMotorClient, name: str) -> AsyncIOMotorDatabase:
    return client[name]
