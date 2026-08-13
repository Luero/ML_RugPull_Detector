# Extract features from any queried token on Eth, BSC, Arbitrum or Polygon using token contract address
# Is used for feature extraction module of the application. Once extracted, features are submitted to the prediction module,
# where the developed model consume them to make a prediction
from feature_extraction_helpers.general_onchain_helpers import get_latest_block
from feature_extraction_helpers.holders_count_helpers import get_holders_snapshots

# Features to extract (based on features list used by the model from the prediction module
#['MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)', 'the number of Transactions', 'Token concentration ratio per holder',
# 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# 'Google results for project x profile (duration/2)', 'project period (days)', 'Holders_12h', 'Holders_24h',
# 'has_contract_swap_patterns', 'has_owner_guard', 'Blockchain Type_POS', 'Blockchain Type_POSA']




# Time for snapshots in hours (only snapshots that are used by the model)
TIME_FOR_SNAPSHOTS_HOURS = (12, 24)



# TODO: latest arbitrum block cached?
# General function to retrieve all on-chain features for a queried token
def extract_onchain_features(chain, token_address):
    # Retrieve latest Arbitrum block to avoid race conditions for multiple users and caching results for live queries, since
    # timing is crucial for them
    latest_arbitrum_block = get_latest_block('ARBI') if chain == 'ARBI' else None
    holder_snapshots = get_holders_snapshots(chain, token_address, TIME_FOR_SNAPSHOTS_HOURS, latest_arbitrum_block)



# TODO: a function for each feature + feeding features into the model