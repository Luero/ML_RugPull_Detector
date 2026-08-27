# Tests for FeatureExtractor

import pytest

import feature_extraction_module.feature_extractor as extractor_module
from feature_extraction_module.feature_extractor import FeatureExtractor
from tests.mock_env import VALID_ADDRESS, LATEST_TS, DEPLOYMENT_TS, make_mock_extraction


# Tests validation of queries before API calls to avoid 'empty' calls
@pytest.mark.parametrize("chain, token_address, expected_error_part", [
    ('POLYGON', VALID_ADDRESS, None),                                           # a valid query
    ('POLYGON', VALID_ADDRESS.upper().replace('0X', '0x'), None),     # a valid query in uppercase hex
    ('SOLANA', VALID_ADDRESS, 'Unsupported blockchain'),                        # unsupported chain
    ('ETH', '0x1234', 'not a valid contract address'),                          # short address
    ('ETH', '0x' + 'g' * 40, 'not a valid contract address'),                   # non-hexadecimal address
    ('ETH', VALID_ADDRESS[2:], 'not a valid contract address'),                 # missing 0x prefix
    ('ETH', None, 'not a valid contract address'),                              # not a string
    ('ETH', '', 'not a valid contract address'),                                # empty string
])
def test_validate_query(chain, token_address, expected_error_part):
    error = FeatureExtractor(chain, token_address).validate_query()
    if expected_error_part is None:
        assert error is None
    else:
        assert expected_error_part in error


# Tests extraction of shared context
@pytest.mark.parametrize("latest_block, deployment_block, expected_error_part", [
    (None, 100, 'unavailable'),                     # a chain provider is down
    (70000000, None, 'No contract deployment'),     # an address is not a contract on this chain
    (70000000, 100, None),                          # successful extraction
])
def test_prepare_shared_context_errors(monkeypatch, latest_block, deployment_block, expected_error_part):
    monkeypatch.setattr(extractor_module, 'get_latest_block_with_timestamp', lambda chain: (latest_block, LATEST_TS if latest_block else None))
    monkeypatch.setattr(extractor_module, 'get_deployment_block_and_timestamp', lambda chain, addr: (deployment_block, DEPLOYMENT_TS if deployment_block else None))
    monkeypatch.setattr(extractor_module, 'get_last_activity_timestamp', lambda chain, addr, latest, dep: int(LATEST_TS.timestamp()) - 3600)
    extractor = FeatureExtractor('POLYGON', VALID_ADDRESS)
    error = extractor.prepare_shared_context()
    if expected_error_part is None:
        assert error is None and extractor.window_end == int(LATEST_TS.timestamp())
    else:
        assert expected_error_part in error


# Tests that the result contains every raw column the model needs and the share context is fetched exactly once per query
def test_extract_features(monkeypatch):
    context_calls = []
    make_mock_extraction(monkeypatch, context_calls)
    result = FeatureExtractor('POLYGON', VALID_ADDRESS).extract_features()
    assert result['error'] is None
    expected_keys = {
        'Blockchain', 'Blockchain Type', 'MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)',
        'the number of Transactions', 'Number of holders', 'project period (days)',
        'Holders_12h', 'Holders_24h', 'has_contract_swap_patterns', 'has_owner_guard',
        'Google results for project website (first day)', 'Google results for project x profile (first days)',
        'Google results for project x profile (duration/2)',
    }
    assert set(result['features']) == expected_keys
    assert result['features']['Blockchain'] == 'POLYGON'
    # each shared value fetched exactly once
    assert context_calls == ['latest', 'deployment', 'activity']
    assert result['missing_features'] == ['Google results for project x profile (duration/2)']


# Tests that an invalid query is rejected before any API call
def test_extract_features_invalid_query_makes_no_calls(monkeypatch):
    context_calls = []
    make_mock_extraction(monkeypatch, context_calls)
    result = FeatureExtractor('POLYGON', 'not-an-address').extract_features()
    assert result['features'] is None and 'not a valid contract address' in result['error']
    assert context_calls == []