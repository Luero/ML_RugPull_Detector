# Testing web interface (offline)

import time

import numpy as np
import pytest

from tests.conftest import VALID_ADDRESS_PATTERN
from ui_module import webapp


# Tests that a root route holds a main page
def test_index_page_is_served(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'Rug-Pull Detector' in response.data
    for element_id in [b'id="predict-form"', b'id="chain"', b'id="token-address"', b'id="predict-button"',
                       b'id="progress"', b'id="error-box"', b'id="result"', b'id="risk-signals"',
                       b'id="missing-warning"', b'id="features-table"']:
        assert element_id in response.data
    assert str(webapp.PREDICTION_THRESHOLD).encode() in response.data
    assert str(webapp.SUSPICION_THRESHOLD).encode() in response.data
    # A band legend shows boundaries in %, matching how the probability is displayed
    assert str(round(webapp.SUSPICION_THRESHOLD * 100)).encode() + b'%' in response.data
    assert str(round(webapp.PREDICTION_THRESHOLD * 100)).encode() + b'%' in response.data


# Tests that invalid input is rejected and returns code 400
@pytest.mark.parametrize('payload', [
    {'chain': 'SOLANA', 'token_address': VALID_ADDRESS_PATTERN},        # unsupported chain
    {'token_address': VALID_ADDRESS_PATTERN},                           # chain missing
    {'chain': 'ETH', 'token_address': '0x123'},                 # address too short
    {'chain': 'ETH', 'token_address': 'a' * 42},                # no 0x prefix
    {'chain': 'ETH', 'token_address': 42},                      # address is not a string
    {'chain': 'ETH'},                                           # address missing
    None,                                                       # no input at all
])
def test_start_prediction_rejects_invalid_input(client, payload):
    response = client.post('/api/predict', json=payload) if payload is not None else client.post('/api/predict')
    assert response.status_code == 400
    assert response.get_json()['error'] is not None
    assert webapp.scan_jobs == {}


# Tests that start of prediction returns code 202 and job id, and result returns with a risk band
def test_prediction_returns_result_with_risk_band(client, monkeypatch):
    monkeypatch.setattr(webapp, 'scan_token', lambda predictor, chain, token_address: {
        'prediction': 'scam', 'scam_probability': 0.9, 'risk_signals': [], 'error': None,
        'features': {'Number of holders': 9}, 'missing_features': []})
    response = client.post('/api/predict', json={'chain': 'ARBI', 'token_address': VALID_ADDRESS_PATTERN})
    assert response.status_code == 202
    job = wait_for_job(client, response.get_json()['job_id'])
    assert job['status'] == 'done'
    assert job['result']['prediction'] == 'scam'
    assert job['result']['scam_probability'] == 0.9
    assert job['result']['risk_band'] == 'high'


# Tests that in case of failure an error message is returned
def test_prediction_with_extraction_error_returns_error(client, monkeypatch):
    monkeypatch.setattr(webapp, 'scan_token', lambda predictor, chain, token_address: {
        'prediction': None, 'scam_probability': None, 'risk_signals': None,
        'features': None, 'missing_features': None, 'error': 'No contract deployment found'})
    response = client.post('/api/predict', json={'chain': 'ETH', 'token_address': VALID_ADDRESS_PATTERN})
    job = wait_for_job(client, response.get_json()['job_id'])
    assert job['status'] == 'done'
    assert job['result']['error'] == 'No contract deployment found'
    assert job['result']['risk_band'] is None


# Tests that nans and numpy values are converted to be stored in the result
def test_prediction_result_is_json_safe(client, monkeypatch):
    monkeypatch.setattr(webapp, 'scan_token', lambda predictor, chain, token_address: {
        'prediction': 'normal', 'scam_probability': 0.1, 'risk_signals': [], 'error': None,
        'features': {'MaxPrice (Quarter 1)': float('nan'), 'Number of holders': np.int64(9),
                     'the number of Transactions': np.float32(116.0)},
        'missing_features': []})
    response = client.post('/api/predict', json={'chain': 'ETH', 'token_address': VALID_ADDRESS_PATTERN})
    job = wait_for_job(client, response.get_json()['job_id'])
    features = job['result']['features']
    assert features['MaxPrice (Quarter 1)'] is None
    assert features['Number of holders'] == 9
    assert features['the number of Transactions'] == 116.0


# Tests that a job is marked as 'failed' in case of crash in extraction
def test_calculate_prediction_marks_crash_as_failed(monkeypatch):
    monkeypatch.setattr(webapp, 'scan_token', raising_error_for_failed_prediction)
    webapp.scan_jobs['job1'] = {'status': 'running', 'chain': 'ETH', 'token_address': VALID_ADDRESS_PATTERN,
                                'result': None, 'error': None}
    webapp.calculate_prediction('job1', 'ETH', VALID_ADDRESS_PATTERN)
    assert webapp.scan_jobs['job1']['status'] == 'failed'
    assert 'Prediction failed!' in webapp.scan_jobs['job1']['error']


# Tests that quering unknown job id results in 404
def test_get_prediction_status_unknown_job_id(client):
    response = client.get('/api/predict/no-such-job')
    assert response.status_code == 404


# Tests that risk bands are distributed correctly
@pytest.mark.parametrize('scam_probability, band', [
    (0.0, 'low'),
    (0.49, 'low'),
    (0.5, 'suspicious'),    # edge case, a boundary for a suspicious token
    (0.576, 'suspicious'),  # right before a 'high' band
    (0.58, 'high'),         # edge case for a 'high' band
    (0.99, 'high'),
    (None, None),           # extraction failed, no probability
])
def test_get_risk_band(scam_probability, band):
    assert webapp.get_risk_band(scam_probability) == band


# Tests that JS scripts call same endpoints the server exposes
def test_index_page_script_calls_existing_api_routes(client):
    response = client.get('/')
    assert b"fetch('/api/predict'" in response.data
    assert b"fetch('/api/predict/' + jobId)" in response.data


# Raising error for a failed prediction
def raising_error_for_failed_prediction(predictor, chain, token_address):
    raise RuntimeError('Prediction failed!')


# Scheduled waiting time to test that job id is returned before completing
def wait_for_job(client, job_id, timeout_seconds=2):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = client.get(f'/api/predict/{job_id}').get_json()
        if job['status'] != 'running':
            return job
        time.sleep(0.01)
    raise AssertionError('scan did not finish in time')