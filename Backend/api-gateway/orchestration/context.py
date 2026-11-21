"""Contexto compartido por los flows con estado (juego en vivo)."""

import asyncio
from dataclasses import dataclass
from typing import Mapping

import httpx


class GameLocks:
    """Un lock por partida: serializa "llamada a Game Logic -> publish" de jugadas, turno del bot,
    rendición y visibilidad. Supone una sola instancia del gateway (igual que los hubs en memoria);
    con varias, el expectedVersion de Game Logic sigue siendo la guarda real de la concurrencia."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def drop(self, key: str) -> None:
        """La partida terminó: se libera su lock (quien ya espera conserva el suyo)."""
        self._locks.pop(key, None)

    def __len__(self) -> int:
        return len(self._locks)


@dataclass(frozen=True)
class Ctx:
    client: httpx.AsyncClient
    upstreams: Mapping[str, str]
    locks: GameLocks
    timeout: float
