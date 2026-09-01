# Testing scan_token function

from prediction_module import scan_token
from tests.conftest import VALID_ADDRESS_PATTERN
from tests.mock_env import MockExtractor, MockPredictor


# Tests failure mode of feature extraction
def test_scan_token_returns_extraction_error(monkeypatch):
    monkeypatch.setattr(scan_token, 'FeatureExtractor', MockExtractor)
    MockExtractor.result = {'features': None, 'missing_features': None, 'error': 'No contract deployment found'}
    MockPredictor.result = None
    result = scan_token.scan_token(MockPredictor(), 'ETH', VALID_ADDRESS_PATTERN)
    assert result == {'scam_probability': None, 'prediction': None, 'risk_signals': None,
                      'features': None, 'missing_features': None, 'error': 'No contract deployment found'}


# Tests that a successful prediction returns a single dictionary with extracted and missing features and prediction result
def test_scan_token_merges_prediction_with_features(monkeypatch):
    monkeypatch.setattr(scan_token, 'FeatureExtractor', MockExtractor)
    MockExtractor.result = {'features': {'Blockchain': 'BSC'}, 'missing_features': ['MaxPrice (Quarter 1)'], 'error': None}
    MockPredictor.result = {'prediction': 'scam', 'scam_probability': 0.9, 'risk_signals': [], 'error': None}
    result = scan_token.scan_token(MockPredictor(), 'BSC', VALID_ADDRESS_PATTERN)
    assert result['prediction'] == 'scam' and result['scam_probability'] == 0.9
    assert result['features'] == {'Blockchain': 'BSC'}
    assert result['missing_features'] == ['MaxPrice (Quarter 1)'] and result['error'] is None


# Tests that a prediction error is returned with extracted features
def test_scan_token_returns_prediction_error_with_features(monkeypatch):
    monkeypatch.setattr(scan_token, 'FeatureExtractor', MockExtractor)
    MockExtractor.result = {'features': {}, 'missing_features': [], 'error': None}
    MockPredictor.result = {'prediction': None, 'scam_probability': None,
                            'risk_signals': None, 'error': 'No features to predict on'}
    result = scan_token.scan_token(MockPredictor(), 'ETH', VALID_ADDRESS_PATTERN)
    assert result['error'] == 'No features to predict on'
    assert result['features'] == {} and result['missing_features'] == []