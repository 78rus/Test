"""Scheduling helper shared by the Qt layer.

Widgets fire-and-forget a lot of coroutines (refresh a directory, run a query,
push a pointer event). Doing that with a bare ``asyncio.ensure_future`` blows up
when no event loop is running yet — which is exactly what happens while the main
window is still being constructed. This helper closes the coroutine instead of
leaking it and reports the situation through a callback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger("cashdesk_control.async")


def schedule(coro: Any, *, on_error: Callable[[str], None] | None = None) -> asyncio.Task[Any] | None:
    """Run *coro* on the current loop, or drop it safely if there is none."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coro.close()
        message = "нет событийного цикла — операция пропущена"
        logger.warning(message)
        if on_error is not None:
            on_error(message)
        return None
    task = loop.create_task(coro)
    task.add_done_callback(_log_failure)
    return task


def _log_failure(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.warning("background task failed: %s", error)


__all__ = ["schedule"]
