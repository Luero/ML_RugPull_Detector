# Testing onchain_extraction_helpers

import math
from datetime import datetime, timezone

import pytest

import feature_extraction_helpers.onchain_extraction_helpers as onchain
from feature_extraction_helpers.config import NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE
from tests.mock_env import FakeSession, FakeResponse

DEPLOYMENT_TS = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
LATEST_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)


# Tests that 'project period (days)' is calculated correctly considering whether a token is live or not
@pytest.mark.parametrize("deployment_block, hours_since_activity, expected", [
    # live token, a period is from deployment to the latest block
    (100, 1, (LATEST_TS - datetime.fromtimestamp(DEPLOYMENT_TS, tz=timezone.utc)).days),
    # dead token, a period ends at the last recorded activity
    (100, 30 * 24, (LATEST_TS - datetime.fromtimestamp(DEPLOYMENT_TS, tz=timezone.utc)).days - 30),
    # no activity ever recorded, a period cannot be determined
    (100, None, None),
    # no deployment block, a period cannot be determined
    (None, 1, None),
])
def test_get_project_period_days(deployment_block, hours_since_activity, expected):
    last_activity = None if hours_since_activity is None \
        else int(LATEST_TS.timestamp()) - hours_since_activity * 3600
    result = onchain.get_project_period_days('ETH', '0xabc', deployment_block, DEPLOYMENT_TS, LATEST_TS, last_activity)
    assert result == expected


# Tests that snapshots are computed only for windows a token has fully lived, incomplete windows become missing values
@pytest.mark.parametrize("token_age_hours, expected_12h, expected_24h, expected_requested_hours", [
    # token younger than every window, both snapshots missing, no extraction attempted
    (6, math.nan, math.nan, None),
    # token older than 12h, but younger than 24h, only complete window (12h) is extracted
    (13, 512, math.nan, (12,)),
    # old token, both windows are extracted
    (100, 512, 524, (12, 24)),
])
def test_get_holders_count_snapshots_young_tokens(monkeypatch, token_age_hours, expected_12h,
                                                  expected_24h, expected_requested_hours):
    requested = []
    monkeypatch.setattr(onchain, 'get_holders_snapshots',
                        lambda chain, addr, hours, block, ts: (requested.append(hours), {f"Holders_{h}h": 500 + h for h in hours})[1])
    latest = datetime.fromtimestamp(DEPLOYMENT_TS + token_age_hours * 3600, tz=timezone.utc)
    result = onchain.get_holders_count_snapshots('ETH', '0xabc', (12, 24), 100, DEPLOYMENT_TS, latest)
    for key, expected in (('Holders_12h', expected_12h), ('Holders_24h', expected_24h)):
        assert result[key] == expected or (isinstance(expected, float) and math.isnan(expected) and math.isnan(result[key]))
    assert requested == ([expected_requested_hours] if expected_requested_hours else [])


# Tests blockchain to consensus type mapping
@pytest.mark.parametrize("chain, expected", [
    ('ETH', 'POS'), ('POLYGON', 'POS'), ('BSC', 'POSA'), ('ARBI', 'Fraud Proofs'),
])
def test_get_blockchain_type(chain, expected):
    assert onchain.get_blockchain_type(chain) == expected


# Tests 'the number of Transactions' for ETH, ARBI and POLYGON chains using Blockscout counters
@pytest.mark.parametrize("counters, expected", [
    ({'transfers_count': '12345', 'token_holders_count': '678'}, 12345),   # normal indexed answer
    ({'token_holders_count': '678'}, None),                                # the field is missing
    (None, None),                                                          # the call failed
])
def test_get_number_of_transactions_from_counters(monkeypatch, counters, expected):
    monkeypatch.setattr(onchain, 'get_token_counters', lambda chain, addr: counters)
    assert onchain.get_number_of_transactions('ETH', '0xabc', 100, 200) == expected


# Tests BSC transfer counting
def test_get_number_of_transactions_bsc(monkeypatch):
    ranges = []
    monkeypatch.setattr(onchain, 'query_meganode',
                        lambda method, params: (ranges.append((int(params[0]['fromBlock'], 16),
                                                               int(params[0]['toBlock'], 16))), hex(10))[1])
    latest_block = NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE + 500
    assert onchain.get_number_of_transactions_bsc('0xabc', 0, latest_block) == 20
    assert ranges == [(0, NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE), (NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE + 1, latest_block)]
    monkeypatch.setattr(onchain, 'query_meganode', lambda method, params: None)
    assert onchain.get_number_of_transactions_bsc('0xabc', 0, 100) is None


# Tests 'Number of holders' for each chain
@pytest.mark.parametrize("chain, payload, expected", [
    # For ETH tokens count comes from Blockscout counters
    ('ETH', {'transfers_count': '1', 'token_holders_count': '678'}, 678),
    # For BSC tokens count comes from NodeReal
    ('BSC', {'result': hex(4321)}, 4321),
    # for BSC with a failed NodeReal call count is a missing value
    ('BSC', None, None),
    # for BSC with an invalid NodeReal response is a missing value
    ('BSC', {'unexpected': 'shape'}, None),
])
def test_get_current_token_holder_count(monkeypatch, chain, payload, expected):
    monkeypatch.setattr(onchain, 'get_token_counters', lambda c, addr: payload)
    monkeypatch.setattr(onchain, 'query_meganode', lambda method, params: payload)
    assert onchain.get_current_token_holder_count(chain, '0xabc') == expected


# Tests Blockscout counters retry
def test_get_token_counters_retries_on_server_error(no_sleep, monkeypatch):
    session = FakeSession([FakeResponse(500, 'oops', is_json=False),
                           FakeResponse(200, {'transfers_count': '5'})])
    monkeypatch.setattr(onchain, 'SESSION', session)
    assert onchain.get_token_counters('ETH', '0xabc') == {'transfers_count': '5'}
    assert len(session.calls) == 2