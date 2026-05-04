"""Global pytest fixtures."""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_pool() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_twilio() -> MagicMock:
    return MagicMock()
