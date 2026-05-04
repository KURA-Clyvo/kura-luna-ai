"""Oracle connection pool — thin mode (no Instant Client required)."""
from contextlib import contextmanager
from typing import Generator

import oracledb


class OracleConnectionPool:
    """Wraps oracledb.ConnectionPool with a safe context-manager accessor."""

    def __init__(self, dsn: str, user: str, password: str) -> None:
        self._pool: oracledb.ConnectionPool = oracledb.create_pool(
            dsn=dsn,
            user=user,
            password=password,
            min=2,
            max=5,
            increment=1,
        )

    @contextmanager
    def get_connection(self) -> Generator[oracledb.Connection, None, None]:
        """Acquire a connection from the pool, releasing it after the block."""
        conn = self._pool.acquire()
        try:
            yield conn
        finally:
            self._pool.release(conn)

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.close()
