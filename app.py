# TODO: general app comment

from feature_extraction_module.feature_extractor import FeatureExtractor
from prediction_module.predictor import Predictor

# TODO: test enrichment scripts

# TODO: test method and move it to other layer (prediction module??)
# Small function to check wiring between Extractor and Predictor
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


def main():
    predictor = Predictor()
    print(scan_token(predictor, 'ETH', '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9'))


if __name__ == "__main__":
    main()
