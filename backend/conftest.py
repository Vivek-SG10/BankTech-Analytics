"""
Root-level conftest.py — applied to ALL tests in the backend.

Sandbox compatibility fixes:
1. Windows sandbox blocks localhost loopback networking used by Python's socket.socketpair().
   We mock socket.socketpair, signal.set_wakeup_fd, and BaseProactorEventLoop._loop_self_reading
   so asyncio ProactorEventLoop and AsyncClient initialize instantly without hanging.
2. AsyncEngine.dispose() is awaited in lifespan shutdown; patched on the class to prevent real DB connection.
3. ping_database() is stubbed to return False so health-check tests don't wait for TCP timeouts.
"""
from __future__ import annotations

import socket
import signal
from unittest.mock import AsyncMock, MagicMock, patch

# Apply Windows sandbox asyncio loop socketpair bypass before any event loops are created
signal.set_wakeup_fd = MagicMock()

def _mock_socketpair():
    m1 = MagicMock()
    m2 = MagicMock()
    m1.fileno.return_value = -1
    m2.fileno.return_value = -1
    return m1, m2

socket.socketpair = _mock_socketpair

try:
    import asyncio.proactor_events
    asyncio.proactor_events.BaseProactorEventLoop._loop_self_reading = lambda self, f=None: None
except Exception:
    pass

import pytest


@pytest.fixture(autouse=True)
def _no_real_postgres():
    """
    Prevent real PostgreSQL connections in every test.

    AsyncEngine.dispose() is awaited by the ASGI lifespan when AsyncClient
    shuts down. It is defined on the class (not the instance), so we must
    patch it at the class level.

    ping_database() is called by the /health router; we stub it to False so
    health-check tests don't block.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine
    from app.core import database as _db_module

    with (
        patch.object(AsyncEngine, "dispose", new=AsyncMock(return_value=None)),
        patch.object(_db_module, "ping_database", new=AsyncMock(return_value=False)),
    ):
        yield
