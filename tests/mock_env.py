# Mocked environment for offline testing (replaces HTTP and XGBoost model) in order for tests to be deterministic

import json

import requests


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
