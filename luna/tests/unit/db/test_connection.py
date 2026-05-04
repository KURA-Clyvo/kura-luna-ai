"""Tests for OracleConnectionPool."""
from unittest.mock import MagicMock, patch, call

import pytest

from src.db.connection import OracleConnectionPool


@patch("src.db.connection.oracledb.create_pool")
def test_pool_created_with_correct_params(mock_create_pool: MagicMock) -> None:
    pool = OracleConnectionPool(dsn="h:1521/X", user="u", password="p")
    mock_create_pool.assert_called_once_with(
        dsn="h:1521/X", user="u", password="p", min=2, max=5, increment=1
    )


@patch("src.db.connection.oracledb.create_pool")
def test_get_connection_acquires_and_releases(mock_create_pool: MagicMock) -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.acquire.return_value = mock_conn
    mock_create_pool.return_value = mock_pool

    oracle_pool = OracleConnectionPool(dsn="h:1521/X", user="u", password="p")
    with oracle_pool.get_connection() as conn:
        assert conn is mock_conn

    mock_pool.acquire.assert_called_once()
    mock_pool.release.assert_called_once_with(mock_conn)


@patch("src.db.connection.oracledb.create_pool")
def test_get_connection_releases_on_exception(mock_create_pool: MagicMock) -> None:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_pool.acquire.return_value = mock_conn
    mock_create_pool.return_value = mock_pool

    oracle_pool = OracleConnectionPool(dsn="h:1521/X", user="u", password="p")

    with pytest.raises(RuntimeError):
        with oracle_pool.get_connection():
            raise RuntimeError("boom")

    mock_pool.release.assert_called_once_with(mock_conn)


@patch("src.db.connection.oracledb.create_pool")
def test_close_delegates_to_pool(mock_create_pool: MagicMock) -> None:
    mock_pool = MagicMock()
    mock_create_pool.return_value = mock_pool

    oracle_pool = OracleConnectionPool(dsn="h:1521/X", user="u", password="p")
    oracle_pool.close()
    mock_pool.close.assert_called_once()
