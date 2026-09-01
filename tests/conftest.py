# Shared fixtures for tests

import pytest
from pathlib import Path
import pandas as pd
import numpy as np

import feature_extraction_module.helpers.general_extraction_helpers as general_helpers
import webapp
from tests.mock_env import MockXGBClassifier
import prediction_module.predictor as predictor_module


# To find prediction module and model itself
PROJECT_ROOT = Path(__file__).parent.parent


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


# Represents live features, based on AIOZ live example, with missing values due to Nans from API responses
@pytest.fixture
def live_features():
    return {
        'Blockchain': 'POLYGON', 'Blockchain Type': 'POS',
        'MaxPrice (Quarter 1)': float('nan'), 'MaxPrice (Quarter 2)': float('nan'),
        'the number of Transactions': 116, 'Number of holders': 9,
        'project period (days)': 943, 'Holders_12h': 1, 'Holders_24h': 1,
        'has_contract_swap_patterns': 0, 'has_owner_guard': 1,
        'Google results for project website (first day)': 633000,
        'Google results for project x profile (first days)': 0,
        'Google results for project x profile (duration/2)': None,
    }


# Enriched dataset, loaded once for each test session
@pytest.fixture(scope='session')
def dataset():
    data = pd.read_excel(PROJECT_ROOT / 'research' / 'data' / 'TM-RugPull_enriched_v.1.0.xlsx')
    data.columns = data.columns.str.strip()
    return data


# Predictor with real model and pre-processors
@pytest.fixture(scope='session')
def real_predictor():
    from prediction_module.predictor import Predictor
    return Predictor(model_path=str(PROJECT_ROOT / 'prediction_module' / 'models' / 'xgboost_model.json'),
                     preprocessing_path=str(PROJECT_ROOT / 'prediction_module' / 'models' / 'preprocessing.joblib'))


# Predictor with real pre-processors but mock model, to test prediction wiring
@pytest.fixture
def mock_model_predictor(monkeypatch):
    monkeypatch.setattr(predictor_module.xgb, 'XGBClassifier', MockXGBClassifier)
    MockXGBClassifier.scam_probability = 0.9
    MockXGBClassifier.contributions = np.zeros(15)
    MockXGBClassifier.captured_inputs = []
    return predictor_module.Predictor(
        model_path=str(PROJECT_ROOT / 'prediction_module' / 'models' / 'xgboost_model.json'),
        preprocessing_path=str(PROJECT_ROOT / 'prediction_module' / 'models' / 'preprocessing.joblib'))


# Clean jobs created for other tests, to start each test fresh
@pytest.fixture(autouse=True)
def clean_scan_jobs():
    webapp.scan_jobs.clear()
    yield
    webapp.scan_jobs.clear()


# Creates a test client for a web part
@pytest.fixture
def client():
    return webapp.app.test_client()
