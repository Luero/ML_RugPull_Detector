# Testing general_extraction_helpers (offline). HTTP is replaced with mocks, no network calls are made

import time
from datetime import datetime, timezone

import pytest

import feature_extraction_module.helpers.general_extraction_helpers as helpers
from tests.mock_env import FakeResponse, FakeSession, RaisingSession

# Scenarios are taken from manual testing and facing with particular error messages and responses
RATE_LIMITED = {'status': '0', 'message': 'NOTOK', 'result': 'Max calls per sec rate limit reached (3/sec)'}
TOKENTX_OK = {'status': '1', 'message': 'OK', 'result': [{'timeStamp': '1700000000'}]}
HTML_503 = FakeResponse(503, '<html><title>503 Service Temporarily Unavailable</title></html>', is_json=False)


# Tests that rate limiter sleeps only the remaining part of the interval
def test_wait_for_rate_limit_sleeps_only_the_remainder(fresh_rate_limiter):
    started = time.monotonic()
    helpers.wait_for_rate_limit('provider-a', 0.2)
    assert time.monotonic() - started < 0.05                                # first call: no sleep
    helpers.wait_for_rate_limit('provider-b', 5.0)      # different provider: independent, no sleep
    assert time.monotonic() - started < 0.1
    helpers.wait_for_rate_limit('provider-a', 0.2)      # first provider again: sleeps the remainder
    assert 0.15 < time.monotonic() - started < 0.4


# Tests query_etherscan for different response scenarios
@pytest.mark.parametrize("responses, expected, expected_calls", [
    # transient rate-limit response is retried and second attempt succeeds
    ([FakeResponse(200, RATE_LIMITED), FakeResponse(200, TOKENTX_OK)], TOKENTX_OK, 2),
    # persistent rate limit gives up after the maximum number of attempts
    ([FakeResponse(200, RATE_LIMITED)] * 3, None, 3),
    # 'not found' message is a valid empty result and is passed through
    ([FakeResponse(200, {'status': '0', 'message': 'No transactions found', 'result': []})],
     {'status': '0', 'message': 'No transactions found', 'result': []}, 1),
    # non-transient API error returns None without retrying
    ([FakeResponse(200, {'status': '0', 'message': 'NOTOK', 'result': 'Missing/Invalid API Key'})], None, 1),
    # HTTP error returns None
    ([FakeResponse(500, {})], None, 1),
])
def test_query_etherscan_scenarios(no_sleep, fresh_rate_limiter, monkeypatch, responses, expected, expected_calls):
    session = FakeSession(responses)
    monkeypatch.setattr(helpers, 'SESSION', session)
    assert helpers.query_etherscan('ETH', {'module': 'account', 'action': 'tokentx'}) == expected
    assert len(session.calls) == expected_calls


# Tests that a rate-limited proxy module response is retried
def test_query_etherscan_proxy_rate_limit_is_retried(no_sleep, fresh_rate_limiter, monkeypatch):
    proxy_ok = {'jsonrpc': '2.0', 'result': '0x10'}
    session = FakeSession([FakeResponse(200, RATE_LIMITED), FakeResponse(200, proxy_ok)])
    monkeypatch.setattr(helpers, 'SESSION', session)
    assert helpers.query_etherscan('ETH', {'module': 'proxy', 'action': 'eth_blockNumber'}) == proxy_ok


# Tests query_geckoterminal retry behaviour, including non-JSON error body that must not crash
@pytest.mark.parametrize("responses, expected_is_none, expected_calls", [
    # status 503 with non-JSON HTML body (real GeckoTerminal behaviour) is retried and then succeeds
    ([HTML_503, FakeResponse(200, {'data': [1]})], False, 2),
    # persistent 503 gives up with None after the maximum number of attempts
    ([HTML_503] * 3, True, 3),
    # non-transient client error returns None without retrying
    ([FakeResponse(400, {'errors': ['bad request']})], True, 1),
])
def test_query_geckoterminal_scenarios(no_sleep, fresh_rate_limiter, monkeypatch, responses, expected_is_none, expected_calls):
    session = FakeSession(responses)
    monkeypatch.setattr(helpers, 'SESSION', session)
    result = helpers.query_geckoterminal('/networks/arbitrum/tokens/0x040d/pools')
    assert (result is None) == expected_is_none
    assert len(session.calls) == expected_calls


# Tests query_moralis retry behaviour
@pytest.mark.parametrize("responses, expected_is_none, expected_calls", [
    # transient 500 ('Unknown error occurred. Please try again') is retried and then succeeds
    ([FakeResponse(500, {'message': 'Unknown error occurred. Please try again or contact support.'}),
      FakeResponse(200, {'result': [1]})], False, 2),
    # 404 means 'no data for this token', returned as None immediately without retrying
    ([FakeResponse(404, {})], True, 1),
])
def test_query_moralis_scenarios(no_sleep, fresh_rate_limiter, monkeypatch, responses, expected_is_none, expected_calls):
    session = FakeSession(responses)
    monkeypatch.setattr(helpers, 'SESSION', session)
    result = helpers.query_moralis('/pairs/0x8c15/ohlcv')
    assert (result is None) == expected_is_none
    assert len(session.calls) == expected_calls


# Tests query_meganode and checks that JSON-RPC payload carries requested method
@pytest.mark.parametrize("response, expected", [
    # a successful call returns result only
    (FakeResponse(200, {'jsonrpc': '2.0', 'result': '0x10'}), '0x10'),
    # a log-limit error triggers range splitting
    (FakeResponse(200, {'jsonrpc': '2.0', 'error': {'message': 'query returned more than 50000 results, logs count exceeds the limit'}}),
     'LOG_LIMIT_EXCEEDED'),
    # any other JSON-RPC error is a failure
    (FakeResponse(200, {'jsonrpc': '2.0', 'error': {'message': 'invalid params'}}), None),
    # a response without result field gives None
    (FakeResponse(200, {'jsonrpc': '2.0'}), None),
    # HTTP error is a failure
    (FakeResponse(500, {}), None),
])
def test_query_meganode_scenarios(no_sleep, fresh_rate_limiter, monkeypatch, response, expected):
    session = FakeSession([response])
    monkeypatch.setattr(helpers, 'SESSION', session)
    assert helpers.query_meganode('eth_getLogs', [{'fromBlock': '0x0'}]) == expected
    assert session.calls[0][1]['json']['method'] == 'eth_getLogs'


# Tests query_coingecko response handling (one call for every scenario (no retry))
@pytest.mark.parametrize("response, expected", [
    # a tracked coin returns its data
    (FakeResponse(200, {'prices': [[1000, 2.5]]}), {'prices': [[1000, 2.5]]}),
    # 404 means a coin is not tracked by CoinGecko
    (FakeResponse(404, {}), None),
    # 401 (demo plan historical depth limit), failure scenario
    (FakeResponse(401, {}), None),
    # a server error is not retried
    (FakeResponse(500, {}), None),
])
def test_query_coingecko_scenarios(no_sleep, fresh_rate_limiter, monkeypatch, response, expected):
    session = FakeSession([response])
    monkeypatch.setattr(helpers, 'SESSION', session)
    assert helpers.query_coingecko('/coins/ethereum/contract/0xabc') == expected
    assert len(session.calls) == 1


# Tests query_dexscreener response handling
@pytest.mark.parametrize("response, expected", [
    # a successful call returns pairs list
    (FakeResponse(200, [{'pairAddress': '0xpool'}]), [{'pairAddress': '0xpool'}]),
    # any non-200 response is a failure scenario
    (FakeResponse(429, {}), None),
])
def test_query_dexscreener_scenarios(monkeypatch, response, expected):
    session = FakeSession([response])
    monkeypatch.setattr(helpers, 'SESSION', session)
    assert helpers.query_dexscreener('/token-pairs/v1/bsc/0xabc') == expected


# Tests that a network-level failure (timeout, connection error) for any query returns error value instead of crashing the whole program
def test_query_helpers_survive_network_exceptions(no_sleep, fresh_rate_limiter, monkeypatch):
    monkeypatch.setattr(helpers, 'SESSION', RaisingSession())
    assert helpers.query_etherscan('ETH', {'module': 'account', 'action': 'tokentx'}) is None
    assert helpers.query_meganode('eth_blockNumber', []) is None
    assert helpers.query_coingecko('/coins/x') is None
    assert helpers.query_geckoterminal('/networks/eth/pools') is None
    assert helpers.query_moralis('/erc20/x') is None
    assert helpers.query_dexscreener('/token-pairs/v1/bsc/0x1') is None
    assert helpers.get_deployment_block_and_timestamp_bsc('0xABC') == (None, None)


# Tests get_block_number_by_timestamp result parsing
@pytest.mark.parametrize("result_value, expected", [
    # normal numeric result is parsed into a block number
    ('76353201', 76353201),
    # Etherscan's error string inside success response must return None
    ('Error! No closest block found', None),
])
def test_get_block_number_by_timestamp_parses_result(no_sleep, fresh_rate_limiter, monkeypatch, result_value, expected):
    session = FakeSession([FakeResponse(200, {'status': '1', 'message': 'OK', 'result': result_value})])
    monkeypatch.setattr(helpers, 'SESSION', session)
    assert helpers.get_block_number_by_timestamp('ARBI', 1624371978) == expected


# Tests binary search on a synthetic chain where block N has timestamp N * 10, must return the closest timestamp
@pytest.mark.parametrize("target_timestamp, expected_block", [
    (55, 5),        # timestamp between blocks
    (50, 5),        # timestamp exactly at a block
    (0, 0),         # timestamp at the very first block
    (2000, 100),    # timestamp after the last block (the upper bound)
])
def test_find_block_by_timestamp_closest_before(monkeypatch, target_timestamp, expected_block):
    monkeypatch.setattr(helpers, 'get_block_timestamp', lambda chain, block: block * 10)
    assert helpers.find_block_by_timestamp('ARBI', target_timestamp, 0, 100) == expected_block


# Tests BSC block-time approximation
@pytest.mark.parametrize("deployment_datetime, expected_block_time", [
    (datetime(2024, 1, 1, tzinfo=timezone.utc), 3.01),      # before the first fork
    (datetime(2025, 4, 29, tzinfo=timezone.utc), 1.50),     # exactly at boundary -> belongs to next period
    (datetime(2025, 10, 1, tzinfo=timezone.utc), 0.75),     # inside a later period
    (datetime(2026, 6, 1, tzinfo=timezone.utc), 0.45),      # the current period
])
def test_get_block_time_seconds_bsc_periods(deployment_datetime, expected_block_time):
    assert helpers.get_block_time_seconds('BSC', deployment_datetime.timestamp()) == expected_block_time


# Tests hours-to-blocks conversion for BSC (12 hours at 3.01 sec/block, truncated to a whole block)
def test_hours_to_blocks_bsc():
    deployment_timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    assert helpers.hours_to_blocks('BSC', 12, deployment_timestamp) == int(12 * 3600 / 3.01)


# Tests determination of a live token (if its last activity is within 72 hours)
@pytest.mark.parametrize("hours_since_activity, expected", [
    (None, False),      # no activity ever recorded -> not live
    (1, True),          # recent activity -> live
    (72, True),         # exactly at 72-hour threshold -> still live
    (73, False),        # beyond the threshold -> dead
])
def test_is_token_live_threshold(hours_since_activity, expected):
    latest_block_timestamp = datetime(2026, 8, 25, tzinfo=timezone.utc)
    last_activity = None if hours_since_activity is None \
        else int(latest_block_timestamp.timestamp()) - hours_since_activity * 3600
    assert helpers.is_token_live(last_activity, latest_block_timestamp) is expected