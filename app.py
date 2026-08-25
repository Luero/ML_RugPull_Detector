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
    print(scan_token(predictor, 'ARBI', '0x040d1edc9569d4bab2d15287dc5a4f10f56a56b8'))


if __name__ == "__main__":
    main()



# For testing - from maxPrices:
# Geckoterminal, success
#     address = '0x100acD9FcD8E0FF80A6595B66fdABe93184Aa100'
#     chain = 'ETH'
#     address = '0xB91025710Adbc140a9fEe4b3E465545a2bF53E20'
#     chain = 'POLYGON'
# CoinGecko has token listed, but does not have price history for required periods (nans for Q1/Q2), fall back to terminal, success
#     address = '0x3cdb41027d61c413e064e84d9c21812b6ef004f1'
#     chain = 'ETH'
# Top pool does not reach window start, use the earliest pool (GeckoTerminal)
#     address = '0x951f086a127e280724fd93ccc543f65065afeb5e'
#     chain = 'ETH'

# 401 for CoinGecko (too deep), fethes proces from Moralis
#     address = '0xb0897686c545045aFc77CF20eC7A532E3120E0F1'
#     chain = 'POLYGON'

# No data in any source:
    # address = '0x0c29891dc5060618c779e2a45fbe4808aa5ae6ad'
    # chain = 'ARBI'

# 'ARBI', '0xa0b862F60edEf4452F25B4160F177db44DeB6Cf1' - GNO

# From extract_osnit_features
# chain, token_address = 'BSC', '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00' - PEPE
# 'ARBI', '0xa0b862F60edEf4452F25B4160F177db44DeB6Cf1' - GNO, big one
# 'POLYGON', '0x06D02e9D62A13fC76BB229373FB3BBBD1101D2fC' - small and recent - None, no socials found
# 'ETH', '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984' - Uniswap, big and old

# From onchain_extractor_helper
# 'BSC', '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00' - PEPE, more than 2 mln transactions
# 'BSC', '0x444045B0EE1ee319A660a5E3d604CA0ffA35ACaA' - BTW, more than 9 mln transactions
# 'BSC', '0x5108C0E857b30A8d191554134628fe0f1B7e78b4' - TITANIA, small one, 90 000 transactions, 8000 holders
# 'ARBI', '0xa0b862F60edEf4452F25B4160F177db44DeB6Cf1' - GNO, big one
# 'POLYGON', '0x06D02e9D62A13fC76BB229373FB3BBBD1101D2fC' - LEO, small and recent
# 'POLYGON', '0xe2341718c6C0CbFa8e6686102DD8FbF4047a9e9B' - AIOZ, small
# 'ARBI', '0xd58D345Fd9c82262E087d2D0607624B410D88242' - TRB, very small (10 holders) - reported by the system as scam
#       difficult, bridge for legitimate project (main project on ETH), profile resembles scam
# 'POLYGON', '0x0C51f415cF478f8D08c246a6C6Ee180C5dC3A012' - on the edge, 0.78 towards scam
# 'POLYGON', '0x6985884C4392D348587B19cb9eAAf157F13271cd' - small, but low scam probability
# 'ETH', '0x7ef1081ecc8b5b5b130656a41d4ce4f89dbbcc8c') - scam, confirmed - model struggling, 0,67 -> normal
# 'BSC', '0xb4c35ff2fb98e9b1bba9d574c6879890f551627c' - scam, confirmed - correct prediction!
# 'BSC', '0x934e1b6db10d8903cd29952081da8cd925c99dd0' - scam, confirmed - correct!