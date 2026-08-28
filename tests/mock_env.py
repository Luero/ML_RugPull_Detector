# Mocked environment for offline testing (replaces HTTP and XGBoost model) in order for tests to be deterministic

import json
from datetime import datetime, timezone
import numpy as np

import requests
import feature_extraction_module.feature_extractor as extractor_module


VALID_ADDRESS = '0x06D02e9D62A13fC76BB229373FB3BBBD1101D2fC'
DEPLOYMENT_TS = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
LATEST_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)


# Single HTTP response
class FakeResponse:
    def __init__(self, status_code, payload, is_json=True):
        self.status_code = status_code
        self._payload = payload
        self._is_json = is_json

    @property
    def text(self):
        return self._payload if isinstance(self._payload, str) else json.dumps(self._payload)

    def json(self):
        if not self._is_json:
            raise requests.exceptions.JSONDecodeError('Expecting value', '<html>', 0)
        return self._payload


# Replace SESSION for expected successful scenarios
class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


# Replaces SESSION for network failures
class RaisingSession:
    def get(self, url, **kwargs):
        raise requests.exceptions.ReadTimeout("Read timed out. (read timeout=30)")

    def post(self, url, **kwargs):
        raise requests.exceptions.ConnectionError("Connection aborted")


# Builds one GeckoTerminal pool entry in the API response shape
def make_pool(token_address, side, reserve, created_at, pool_address):
    token_id = f"eth_{token_address}"
    return {
        'attributes': {'reserve_in_usd': reserve, 'pool_created_at': created_at, 'address': pool_address},
        'relationships': {
            'base_token': {'data': {'id': token_id if side == 'base' else 'eth_0xother'}},
            'quote_token': {'data': {'id': token_id if side == 'quote' else 'eth_0xother'}},
        },
    }


# Imitates feature extraction for each group of features
def make_mock_extraction(monkeypatch, context_calls):
    monkeypatch.setattr(extractor_module, 'get_latest_block_with_timestamp',
                        lambda chain: (context_calls.append('latest'), (70000000, LATEST_TS))[1])
    monkeypatch.setattr(extractor_module, 'get_deployment_block_and_timestamp',
                        lambda chain, addr: (context_calls.append('deployment'), (60000000, DEPLOYMENT_TS))[1])
    monkeypatch.setattr(extractor_module, 'get_last_activity_timestamp',
                        lambda chain, addr, latest, dep: (context_calls.append('activity'), int(LATEST_TS.timestamp()) - 3600)[1])
    monkeypatch.setattr(extractor_module, 'get_max_price_quarters_live',
                        lambda chain, addr, dep_ts, window_end: {'MaxPrice (Quarter 1)': 2.5, 'MaxPrice (Quarter 2)': 3.5,
                                                                 'price_source': 'coingecko', 'window_start': DEPLOYMENT_TS + 100})
    monkeypatch.setattr(extractor_module, 'get_onchain_features_live',
                        lambda *args: {'project period (days)': 151, 'the number of Transactions': 116,
                                       'Number of holders': 9, 'Blockchain Type': 'POS',
                                       'Holders_12h': 1, 'Holders_24h': 1})
    monkeypatch.setattr(extractor_module, 'get_source_code_features_live',
                        lambda chain, addr: {'has_contract_swap_patterns': 0, 'has_owner_guard': 1})
    monkeypatch.setattr(extractor_module, 'get_osint_features_live',
                        lambda chain, addr, trading_start, window_end: {
                            'Google results for project website (first day)': 633000,
                            'Google results for project x profile (first days)': 0,
                            'Google results for project x profile (duration/2)': None})


# Imitates XGBClassifier, returns scam probability and contributions for each feature
class MockXGBClassifier:
    # Set by tests after object initiation
    scam_probability = 0.9
    contributions = None
    captured_inputs = []
    # matches the winning model
    n_features_in_ = 14

    def load_model(self, path):
        self.loaded_from = path

    def predict_proba(self, X):
        MockXGBClassifier.captured_inputs.append(X)
        return np.array([[1 - MockXGBClassifier.scam_probability, MockXGBClassifier.scam_probability]])

    def get_booster(self):
        return MockBooster()


class MockBooster:
    def predict(self, dmatrix, pred_contribs=False):
        assert pred_contribs
        contribs = MockXGBClassifier.contributions
        if contribs is None:
            contribs = np.zeros(15)
        return np.array([contribs])
