# Scans a queried token using Predictor, serves as a layer between Feature extraction module and Prediction modules.
# It is located in a prediction_module, since the app is too small to introduce a separate middle layer. However,
# in case of scaling this functionality should move between feature_extraction_module and prediction modules and UI.

from feature_extraction_module.feature_extractor import FeatureExtractor

# TODO: test enrichment scripts

# TODO: test method
# Wire Extractor and Predictor
def scan_token(predictor, chain, token_address):
    extraction = FeatureExtractor(chain, token_address).extract_features()
    if extraction['error'] is not None:
        return {'scam_probability': None, 'prediction': None, 'risk_signals': None,
                'features': None, 'missing_features': None, 'error': extraction['error']}

    result = predictor.predict(extraction['features'])
    # Extracted features are captured for analysis
    result['features'] = extraction['features']
    result['missing_features'] = extraction['missing_features']

    return result
