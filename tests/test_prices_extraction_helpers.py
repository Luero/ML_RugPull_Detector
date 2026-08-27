# Testing prices_extraction_helpers. All price sources are mocked

import math
import time
from datetime import datetime, timezone

import pytest

import feature_extraction_helpers.prices_extraction_helpers as prices
from feature_extraction_helpers.config import GECKOTERMINAL_MAX_DEPTH_SECONDS
from tests.mock_env import make_pool

WINDOW_START = 1000
# quarter length = 1000
WINDOW_END = 5000


# Tests search of maximum price within two time boundaries
@pytest.mark.parametrize("price_points, from_timestamp, to_timestamp, expected", [
    # base case (maximum prices are inside the range)
    ([(10, 1.0), (20, 3.0), (30, 2.0)], 10, 40, 3.0),
    # edge case (start is inclusive, end is exclusive)
    ([(10, 1.0), (20, 3.0)], 10, 20, 1.0),
    # no prices inside the range, leads to missing value
    ([(10, 1.0)], 50, 60, math.nan),
    # empty price list, missing value
    ([], 0, 100, math.nan),
])
def test_get_max_price_in_range(price_points, from_timestamp, to_timestamp, expected):
    result = prices.get_max_price_in_range(price_points, from_timestamp, to_timestamp)
    assert result == expected or (math.isnan(expected) and math.isnan(result))


# Tests quarter splitting
@pytest.mark.parametrize("price_points, expected_q1, expected_q2", [
    # one point in each quarter, so each quarter reports its maximum
    ([(1500, 2.0), (2500, 7.0)], 2.0, 7.0),
    # prices only in Q1, Q2 becomes a missing value
    ([(1500, 2.0)], 2.0, math.nan),
    # zero prices are valid values
    ([(1500, 0.0), (2500, 0.0)], 0.0, 0.0),
])
def test_compute_quarters(price_points, expected_q1, expected_q2):
    result = prices.compute_quarters(price_points, WINDOW_START, WINDOW_END, 'coingecko')
    for key, expected in (('MaxPrice (Quarter 1)', expected_q1), ('MaxPrice (Quarter 2)', expected_q2)):
        assert result[key] == expected or (math.isnan(expected) and math.isnan(result[key]))
    assert result['price_source'] == 'coingecko'


# Tests zero or negative time window
@pytest.mark.parametrize("window_end", [
    WINDOW_START,                    # no window at all (zero window)
    WINDOW_START - 100,              # negative window (end before start)
])
def test_compute_quarters_invalid_window(window_end):
    result = prices.compute_quarters([(1500, 2.0)], WINDOW_START, window_end, 'coingecko')
    assert math.isnan(result['MaxPrice (Quarter 1)']) and math.isnan(result['MaxPrice (Quarter 2)'])


# Tests GeckoTerminal candle resolution depending on time window length
@pytest.mark.parametrize("window_seconds, expected", [
    (3600, ('second', 30)),                # short window -> 30-second candles
    (2 * 24 * 3600, ('second', 30)),       # exactly two days (edge case) -> 30-second candles
    (2 * 24 * 3600 + 1, ('hour', 1)),      # right after two days -> hourly candles
    (61 * 24 * 3600, ('day', 1)),          # over sixty days -> daily candles
])
def test_choose_ohlcv_timeframe_gecko(window_seconds, expected):
    assert prices.choose_ohlcv_timeframe_gecko(window_seconds) == expected


# Tests timestamp parsers
def test_timestamp_parsers():
    expected = int(datetime(2022, 2, 9, 6, 32, 1, tzinfo=timezone.utc).timestamp())
    assert prices.parse_pool_created_at('2022-02-09T06:32:01Z') == expected
    assert prices.parse_moralis_timestamp('2022-02-09T06:32:01.000Z') == expected


# Tests observation window end (query time for live tokens, last activity for dead tokens)
@pytest.mark.parametrize("hours_since_activity, expected_end", [
    (1, 'latest'),              # live token, a window ends at query time (latest block)
    (100, 'activity'),          # dead token, a window ends at the last recorded activity
    (None, 'latest'),           # no activity ever, use query time
])
def test_get_window_end_timestamp(hours_since_activity, expected_end):
    latest_block_timestamp = datetime(2026, 8, 25, tzinfo=timezone.utc)
    last_activity = None if hours_since_activity is None \
        else int(latest_block_timestamp.timestamp()) - hours_since_activity * 3600
    result = prices.get_window_end_timestamp(latest_block_timestamp, last_activity)
    expected = int(latest_block_timestamp.timestamp()) if expected_end == 'latest' else last_activity
    assert result == expected


# Tests pool selection logic
def test_get_top_pool_address_selection(monkeypatch):
    token = '0xabc'
    payload = {'data': [
        make_pool(token, 'base', '100', '2022-05-01T00:00:00Z', '0xpool-top'),
        make_pool(token, 'quote', '50', '2022-01-01T00:00:00Z', '0xpool-earliest'),
        make_pool('0xUNRELATED', 'base', '900', '2021-01-01T00:00:00Z', '0xpool-foreign'),  # must be ignored
    ]}
    monkeypatch.setattr(prices, 'query_geckoterminal', lambda endpoint, params=None: payload)
    top, earliest_created, earliest, top_side, earliest_side = prices.get_top_pool_address('ETH', token)
    assert (top, earliest) == ('0xpool-top', '0xpool-earliest')
    assert earliest_created == '2022-01-01T00:00:00Z'
    assert (top_side, earliest_side) == ('base', 'quote')


# Tests pool selection edge cases
@pytest.mark.parametrize("payload", [
    # API returned nothing for this token
    {'data': []},
    # pools exist, but without a creation date, so the window start cannot be determined
    None,      # built during test by make_pool
])
def test_get_top_pool_address_empty_cases(monkeypatch, payload):
    if payload is None:
        payload = {'data': [make_pool('0xabc', 'base', '100', None, '0xpool')]}
    monkeypatch.setattr(prices, 'query_geckoterminal', lambda endpoint, params=None: payload)
    assert prices.get_top_pool_address('ETH', '0xabc') == (None, None, None, None, None)


# Tests that the earliest pool timestamp is used for window start
def test_get_max_price_quarters_live_uses_earliest_pool(monkeypatch):
    pool_created = '2022-01-01T00:00:00Z'
    pool_timestamp = prices.parse_pool_created_at(pool_created)
    coingecko_ranges = []
    monkeypatch.setattr(prices, 'get_top_pool_address',
                        lambda chain, addr: ('0xtop', pool_created, '0xearliest', 'base', 'base'))
    monkeypatch.setattr(prices, 'get_prices_coingecko',
                        lambda chain, addr, f, t: (coingecko_ranges.append((f, t)), [(f + 10, 7.0)])[1])
    result = prices.get_max_price_quarters_live('ETH', '0xabc', 1600000000, pool_timestamp + 4000)
    assert result['window_start'] == pool_timestamp
    assert coingecko_ranges == [(pool_timestamp, pool_timestamp + 4000)]
    assert result['MaxPrice (Quarter 1)'] == 7.0 and result['price_source'] == 'coingecko'


# Tests that without any pool deployment timestamp is used
def test_get_max_price_quarters_live_use_deployment(monkeypatch):
    deployment_timestamp = 1600000000
    monkeypatch.setattr(prices, 'get_top_pool_address', lambda chain, addr: (None, None, None, None, None))
    monkeypatch.setattr(prices, 'get_prices_coingecko', lambda chain, addr, f, t: None)
    result = prices.get_max_price_quarters_live('ETH', '0xabc', deployment_timestamp, deployment_timestamp + 4000)
    assert math.isnan(result['MaxPrice (Quarter 1)']) and result['price_source'] is None
    assert result['window_start'] == deployment_timestamp


# Tests that sources of data are used in right order
def test_geckoterminal_or_moralis_ordering(monkeypatch):
    now = int(time.time())
    monkeypatch.setattr(prices, 'get_ohlcv_history',
                        lambda chain, pool, f, t, side: ([[f + 10, 1, 2, 0.5, 1.5, 100]], False))
    monkeypatch.setattr(prices, 'get_prices_defillama', lambda chain, addr, f, t: [(f + 10, 3.5)])
    monkeypatch.setattr(prices, 'get_prices_moralis_pair', lambda chain, pair, f, t: ([(f + 10, 2.5)], False))
    # within the depth limit, GeckoTerminal candles, DeFiLlama not consulted
    recent_start = now - 10 * 24 * 3600
    result, source = prices.try_geckoterminal_defilama_or_moralis('ETH', '0xabc', recent_start, now, '0xtop', '0xearliest', 'base', 'base')
    assert source == 'geckoterminal' and result == [(recent_start + 10, 1.5)]
    # beyond the depth limit, DeFiLlama is tried first
    old_start = now - GECKOTERMINAL_MAX_DEPTH_SECONDS - 1000
    result, source = prices.try_geckoterminal_defilama_or_moralis('ETH', '0xabc', old_start, now, '0xtop', '0xearliest', 'base', 'base')
    assert source == 'defillama' and result == [(old_start + 10, 3.5)]
    # beyond the depth limit with a token DeFiLlama does not track, falls back to Moralis
    monkeypatch.setattr(prices, 'get_prices_defillama', lambda chain, addr, f, t: None)
    result, source = prices.try_geckoterminal_defilama_or_moralis('ETH', '0xabc', old_start, now, '0xtop', '0xearliest', 'base', 'base')
    assert source == 'moralis' and result == [(old_start + 10, 2.5)]
    assert prices.try_geckoterminal_defilama_or_moralis('ETH', '0xabc', recent_start, now, None, None, None, None) == (None, None)