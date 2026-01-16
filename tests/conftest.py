"""
Pytest configuration and fixtures.

Shared fixtures for all tests.
"""

import pytest
import os
from pathlib import Path
import tempfile
import shutil

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["ALPACA_API_KEY"] = "test_key"
os.environ["ALPACA_SECRET_KEY"] = "test_secret"


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def mock_alpaca_client(monkeypatch):
    """Mock Alpaca client for testing."""
    from unittest.mock import Mock
    
    mock_client = Mock()
    mock_client.get_account.return_value = Mock(equity=100000.0, cash=100000.0)
    mock_client.get_positions.return_value = []
    mock_client.get_clock.return_value = Mock(is_open=True)
    mock_client.get_historical_bars.return_value = []
    
    return mock_client


@pytest.fixture
def sample_bars():
    """Create sample bar data for testing."""
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    
    dates = pd.date_range(
        start=datetime.now() - timedelta(days=100),
        end=datetime.now(),
        freq="D",
    )
    
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(len(dates)) * 2)
    
    return pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.random.randint(1000000, 5000000, len(dates)),
        "symbol": "TEST",
    })
