# Contains a class aimed to combine all feature extraction helpers into a singe pipeline.
# It needs a chain and a token address.
# Firstly, extracts token's shared context (values that are re-used later in different extraction scripts),
# then in extract_features calls feature extraction functions one by one (prices -> onchain -> source code -> OSINT).
# Returns a dictionary with extracted features, named as relevant features in the dataset, to be consumed by prediction module.


from feature_extraction_helpers.source_code_helplers import get_source_code_features_live
from feature_extraction_helpers.onchain_extraction_helpers import get_onchain_features_live
from feature_extraction_helpers.prices_extraction_helpers import get_max_price_quarters_live, get_window_end_timestamp
from feature_extraction_helpers.osnit_extraction_helpers import get_osint_features_live
from feature_extraction_helpers.general_extraction_helpers import get_latest_block_with_timestamp, \
    get_deployment_block_and_timestamp, get_last_activity_timestamp


# Call all extraction scripts for a single query using chain and token address
class FeatureExtractor:
    def __init__(self, chain, token_address):
        self.chain = chain
        self.token_address = token_address
        # Shared context, got once for query and reused it all extraction functions
        self.latest_block = None
        self.latest_block_timestamp = None
        self.deployment_block = None
        self.deployment_timestamp = None
        self.last_activity_timestamp = None
        self.window_end = None


    # Retrieve variables that are reused by all extraction functions
    # Returns False if failed
    def prepare_shared_context(self):
        print("Retrieving shared context...")
        # The latest block is used as 'now' point at time to extract values at the time of query and reuses them
        # for all features for consistency (not separate calls for the last block per feature, as blocks may appear during API calls execution)
        self.latest_block, self.latest_block_timestamp = get_latest_block_with_timestamp(self.chain)
        if self.latest_block is None:
            print(f"...Could not get the latest block for {self.chain}")
            return False
        self.deployment_block, self.deployment_timestamp = get_deployment_block_and_timestamp(self.chain, self.token_address)
        if self.deployment_block is None:
            print(f"...Could not get deployment info for {self.token_address} on {self.chain}")
            return False
        self.last_activity_timestamp = get_last_activity_timestamp(self.chain, self.token_address, self.latest_block, self.deployment_block)
        self.window_end = get_window_end_timestamp(self.latest_block_timestamp, self.last_activity_timestamp)
        return True


    # Extract all features consumed by the prediction module for a queried token
    # Returns a dictionary with dataset column names or None if shared context is not retrieved
    def extract_features(self):
        if not self.prepare_shared_context():
            return None
        features = {'Blockchain': self.chain}

        # Price features extraction, also resolves window_start (the first trading activity based on the earliest pool creation)
        price_features = get_max_price_quarters_live(self.chain, self.token_address, self.deployment_timestamp, self.window_end)
        features['MaxPrice (Quarter 1)'] = price_features['MaxPrice (Quarter 1)']
        features['MaxPrice (Quarter 2)'] = price_features['MaxPrice (Quarter 2)']

        # On-chain features ('project period (days)', 'the number of Transactions', 'Number of holders',
        # 'Holders_12h', 'Holders_24h', 'Blockchain Type')
        onchain_features = get_onchain_features_live(self.chain, self.token_address, self.deployment_block,
                                                     self.deployment_timestamp, self.latest_block,
                                                     self.latest_block_timestamp, self.last_activity_timestamp)
        features.update(onchain_features)

        # Code-based features ('has_contract_swap_patterns', 'has_owner_guard')
        source_code_features = get_source_code_features_live(self.chain, self.token_address)
        features.update(source_code_features)

        # Off-chain (OSINT) features (window_start from price extraction is used as the start of trading activity
        # (consistent with TM-RugPull methodology), deployment timestamp as a fallback)
        trading_start_timestamp = price_features.get('window_start') or self.deployment_timestamp
        osint_features = get_osint_features_live(self.chain, self.token_address, trading_start_timestamp, self.window_end)
        features.update(osint_features)

        return features


def main():
    extractor = FeatureExtractor('ETH', '0x3cdb41027d61c413e064e84d9c21812b6ef004f1')
    features = extractor.extract_features()
    print(features)


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
# 'BSC', '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00') - PEPE, more than 2 mln transactions
# 'BSC', '0x444045B0EE1ee319A660a5E3d604CA0ffA35ACaA' - BTW, more than 9 mln transactions
# 'BSC', '0x5108C0E857b30A8d191554134628fe0f1B7e78b4' - TITANIA, small one, 90 000 transactions, 8000 holders
# 'ARBI', '0xa0b862F60edEf4452F25B4160F177db44DeB6Cf1' - GNO, big one
# 'POLYGON', '0x06D02e9D62A13fC76BB229373FB3BBBD1101D2fC' - LEO, small and recent