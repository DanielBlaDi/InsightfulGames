"""Contexto compartido por los flows con estado (juego en vivo)."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Coroutine, Mapping

import httpx

logger = logging.getLogger("gateway.orchestration")


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


class BackgroundTasks:
    """Tareas que deben terminar aunque el cliente se desconecte (una jugada ya aceptada por Game Logic no
    puede quedar a medias). Se conservan aquí para que nadie las cancele y se espera por ellas al apagar."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def __len__(self) -> int:
        return len(self._tasks)

    async def drain(self, timeout: float) -> None:
        """Espera a las tareas pendientes (hasta `timeout` segundos) y cancela las que no terminen."""
        pending = list(self._tasks)
        if not pending:
            return
        _, still = await asyncio.wait(pending, timeout=timeout)
        for task in still:
            task.cancel()
        if still:
            logger.warning("Se cancelaron %s tareas que no terminaron al apagar", len(still))
            await asyncio.gather(*still, return_exceptions=True)


@dataclass(frozen=True)
class Ctx:
    client: httpx.AsyncClient
    upstreams: Mapping[str, str]
    locks: GameLocks
    timeout: float
    tasks: BackgroundTasks = field(default_factory=BackgroundTasks)
