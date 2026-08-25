from feature_extraction_module.feature_extractor import FeatureExtractor
from prediction_module.predictor import Predictor


# Small function to check wiring between Extractor and Predictor
def scan_token(predictor, chain, token_address):
    extraction = FeatureExtractor(chain, token_address).extract_features()
    if extraction['error'] is not None:
        return {'scam_probability': None, 'prediction': None, 'risk_signals': None,
                'missing_features': None, 'error': extraction['error']}

    result = predictor.predict(extraction['features'])
    result['missing_features'] = extraction['missing_features']

    return result


def main():
    predictor = Predictor()
    print(scan_token(predictor, 'ARBI', '0xd58D345Fd9c82262E087d2D0607624B410D88242'))


if __name__ == "__main__":
    main()