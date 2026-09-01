# Testing osnit_extraction_helpers

from datetime import datetime, timezone

import pytest

import feature_extraction_module.helpers.osnit_extraction_helpers as osint
from tests.mock_env import FakeResponse, FakeSession


# Based on real SerpAPI response
NO_RESULTS_ERROR = {'error': "Google hasn't returned any results for this query."}
TRADING_START = int(datetime(2022, 3, 1, tzinfo=timezone.utc).timestamp())    # before Twitter rebranding
WINDOW_END = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp())       # after Twitter (X) rebranding


# Tests X handle normalisation
@pytest.mark.parametrize("raw_value, expected", [
    ('https://twitter.com/WeAreTellor', 'WeAreTellor'),     # full Twitter URL
    ('https://x.com/pepe?lang=en', 'pepe'),                 # X URL with a query string
    ('http://www.twitter.com/gnosisdao/', 'gnosisdao'),     # www prefix and trailing slash
    ('@handle_1', 'handle_1'),                              # bare handle with @
    ('handle_1', 'handle_1'),                               # bare handle
    (None, None),                                           # nothing provided
    ('', None),                                             # empty string
    ('twitter.com', None),                                  # domain without a handle
])
def test_normalise_x_handle(raw_value, expected):
    assert osint.normalize_x_handle(raw_value) == expected


# Tests that the search term uses the domain that existed at the target date
@pytest.mark.parametrize("target_timestamp, expected_domain", [
    (osint.X_REBRAND_TIMESTAMP - 1, 'twitter.com'),     # the day before rebranding
    (osint.X_REBRAND_TIMESTAMP, 'x.com'),               # exactly at rebranding date (inclusive)
    (osint.X_REBRAND_TIMESTAMP + 1, 'x.com'),           # after the rebranding
])
def test_build_x_profile_search_term(target_timestamp, expected_domain):
    assert osint.build_x_profile_search_term('handle', target_timestamp) == f"{expected_domain}/handle"


# Tests timestamp conversion to SerpAPI date format (MM/DD/YYYY, UTC)
def test_convert_date():
    assert osint.convert_cdr_date(int(datetime(2022, 3, 9, 23, 59, tzinfo=timezone.utc).timestamp())) == '03/09/2022'


# Tests midpoint calculation
@pytest.mark.parametrize("window_end, expected", [
    (2000, 1500),   # normal window -> the arithmetic midpoint
    (1000, 1000),   # start and end at the same time -> the midpoint is start
])
def test_get_midpoint_timestamp(window_end, expected):
    assert osint.get_midpoint_timestamp(1000, window_end) == expected


# Tests Google result counts
@pytest.mark.parametrize("response, expected", [
    # SerpApi reports 'Google found nothing', meaning 0 results (not None)
    (FakeResponse(200, NO_RESULTS_ERROR), 0),
    # Empty search result, also mean 0 results
    (FakeResponse(200, {'search_information': {'organic_results_state': 'Fully empty'}}), 0),
    # total results found
    (FakeResponse(200, {'search_information': {'total_results': 123}}), 123),
    # HTTP error, return None
    (FakeResponse(500, {}), None),
])
def test_get_google_result_count(monkeypatch, response, expected):
    monkeypatch.setattr(osint, 'SESSION', FakeSession([response]))
    assert osint.get_google_result_count('twitter.com/WeAreTellor', TRADING_START) == expected


# Tests socials resolution order (Moralis -> CoinGecko -> DEXScreener), partial answers are merged
def test_get_project_socials_merges_sources(monkeypatch):
    called_sources = []
    monkeypatch.setattr(osint, 'get_project_socials_moralis',
                        lambda chain, addr: (called_sources.append('moralis'), ('https://site.org', None))[1])
    monkeypatch.setattr(osint, 'get_project_socials_coingecko',
                        lambda chain, addr: (called_sources.append('coingecko'), (None, 'handle_1'))[1])
    monkeypatch.setattr(osint, 'get_project_socials_dexscreener',
                        lambda chain, addr: (called_sources.append('dexscreener'), (None, None))[1])
    assert osint.get_project_socials('ETH', '0xabc') == ('https://site.org', 'handle_1')
    # DEXScreener not needed, must be skipped
    assert called_sources == ['moralis', 'coingecko']


# Tests that unresolved socials produce missing values for all three Google features
def test_get_osint_features_live_unresolved_socials(monkeypatch):
    monkeypatch.setattr(osint, 'get_project_socials', lambda chain, addr: (None, None))
    result = osint.get_osint_features_live('ETH', '0xabc', TRADING_START, WINDOW_END)
    assert result == {'Google results for project website (first day)': None,
                      'Google results for project x profile (first days)': None,
                      'Google results for project x profile (duration/2)': None}


# Tests scenario, when social are resolved, but no search results within time window are found, expect 0 results
def test_get_osint_features_live_zero_results_and_rebranding(monkeypatch):
    searched_terms = []
    monkeypatch.setattr(osint, 'get_project_socials', lambda chain, addr: ('https://site.org', 'WeAreTellor'))
    monkeypatch.setattr(osint, 'get_google_result_count', lambda term, ts: (searched_terms.append(term), 0)[1])
    result = osint.get_osint_features_live('ETH', '0xabc', TRADING_START, WINDOW_END)
    assert set(result.values()) == {0}
    assert searched_terms == ['https://site.org', 'twitter.com/WeAreTellor', 'x.com/WeAreTellor']