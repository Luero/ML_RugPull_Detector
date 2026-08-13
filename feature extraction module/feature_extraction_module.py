# Extract features from any queried token on Eth, BSC, Arbitrum or Polygon using token contract address
# Is used for feature extraction module of the application. Once extracted, features are submitted to the prediction module,
# where the developed model consume them to make a prediction


# Features to extract (based on features list used by the model from the prediction module
#['MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)', 'the number of Transactions', 'Token concentration ratio per holder',
# 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# 'Google results for project x profile (duration/2)', 'project period (days)', 'Holders_12h', 'Holders_24h',
# 'has_contract_swap_patterns', 'has_owner_guard', 'Blockchain Type_POS', 'Blockchain Type_POSA']


import os

# TODO: refactor to put all these into some config file into a reusable library??
# Sources of data
# https://docs.etherscan.io/api-reference
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
ETHERSCAN_BASE_URL = 'https://api.etherscan.io/v2/api'

# https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
NODEREAL_API_KEY = os.getenv('NODEREAL_API_KEY')
MEGANODE_BSC_URL = (f'https://bsc-mainnet.nodereal.io/v1/{NODEREAL_API_KEY}')

# IDs of chains supported by Etherscan and relevant for the dataset
# Reference: https://docs.etherscan.io/supported-chains
CHAIN_IDS = {'ETH': 1, 'POLYGON': 137, 'ARBI': 42161}


# TODO: a function for each feature + feeding features into the model