# Contains a class aimed to combine all feature extraction helpers into a singe pipeline.
# It needs a chain and a token address.
# Firstly, extracts token's shared context (values that are re-used later in different extraction scripts),
# then in extract_features calls feature extraction functions one by one (prices -> onchain -> source code -> OSINT).
# Returns a dictionary with extracted features, named as relevant features in the dataset, to be consumed by prediction module.

import math

from feature_extraction_module.helpers.config import ETHERSCAN_CHAIN_IDS, CONTRACT_ADDRESS_PATTERN
from feature_extraction_module.helpers.source_code_helplers import get_source_code_features_live
from feature_extraction_module.helpers.onchain_extraction_helpers import get_onchain_features_live
from feature_extraction_module.helpers.prices_extraction_helpers import get_max_price_quarters_live, get_window_end_timestamp
from feature_extraction_module.helpers.osnit_extraction_helpers import get_osint_features_live
from feature_extraction_module.helpers.general_extraction_helpers import get_latest_block_with_timestamp, \
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


    # Validate submitted query before any API call is made
    def validate_query(self):
        if self.chain not in ETHERSCAN_CHAIN_IDS:
            return f"Unsupported blockchain '{self.chain}', supported: {', '.join(ETHERSCAN_CHAIN_IDS)}"
        if not isinstance(self.token_address, str) or not CONTRACT_ADDRESS_PATTERN.match(self.token_address):
            return f"'{self.token_address}' is not a valid contract address: '0x' followed by 40 hexadecimal characters is expected"
        return None


    # Retrieve variables that are reused by all extraction functions
    # Returns None, if success, and an error message if failure
    def prepare_shared_context(self):
        print("Retrieving shared context...")
        # The latest block is used as 'now' point at time to extract values at the time of query and reuses them
        # for all features for consistency (not separate calls for the last block per feature, as blocks may appear during API calls execution)
        self.latest_block, self.latest_block_timestamp = get_latest_block_with_timestamp(self.chain)
        if self.latest_block is None:
            return f"Latest block for {self.chain} is unavailable, try again later"
        self.deployment_block, self.deployment_timestamp = get_deployment_block_and_timestamp(self.chain, self.token_address)
        if self.deployment_block is None:
            return f"No contract deployment found for {self.token_address} on {self.chain} (wrong blockchain or not a token contract address)"
        self.last_activity_timestamp = get_last_activity_timestamp(self.chain, self.token_address, self.latest_block, self.deployment_block)
        self.window_end = get_window_end_timestamp(self.latest_block_timestamp, self.last_activity_timestamp)
        return None


    # Extract all features consumed by the prediction module for a queried token
    # Returns a dictionary with:
    # - 'features' (extracted features with dataset column names or None if extraction failed);
    # - 'missing_features' (names of features that could not be extracted (so UI can warn user);
    # - 'error' (explanation for UI when extraction failed)
    def extract_features(self):
        error = self.validate_query()
        if error is None:
            error = self.prepare_shared_context()
        if error is not None:
            print(error)
            return {'features': None, 'missing_features': None, 'error': error}
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

        # Features that could not be extracted, so UI can report completeness of data
        missing_features = sorted(name for name, value in features.items() if value is None or (isinstance(value, float) and math.isnan(value)))

        return {'features': features, 'missing_features': missing_features, 'error': None}