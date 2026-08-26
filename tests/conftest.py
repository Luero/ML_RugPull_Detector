# Shared fixtures for tests

import pytest

import feature_extraction_helpers.general_extraction_helpers as general_helpers


# Disable sleeping to run tests instantly
@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr('time.sleep', lambda seconds: None)


# Clear rate limiter state
@pytest.fixture
def fresh_rate_limiter():
    general_helpers.LAST_CALL_TIMES.clear()
    yield
    general_helpers.LAST_CALL_TIMES.clear()
