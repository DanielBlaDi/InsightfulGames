"""Conexión a MongoDB de análisis.

El Analysis Worker es la única excepción a la regla de que ningún servicio
escribe en la base de otro (contrato, sección 17.7). Solo actualiza los campos
acotados del documento de análisis.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

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
