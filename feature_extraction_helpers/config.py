# TODO: general comment

import os

from dotenv import load_dotenv

load_dotenv()

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

# https://www.4byte.directory/event-signatures/?bytes_signature=0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
TRANSFER_EVENT_HASH = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

# Etherscan free-tier limit on records per getLogs call: https://docs.etherscan.io/changelog
ETH_LOG_RESULT_LIMIT = 1000
# NodeReal limitations for block range size and number of records returned: https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
NODEREAL_BLOCK_RANGE_SIZE = 49000

# API limitations for calls per time
ETHERSCAN_TIME_INTERVAL = 0.35
NODEREAL_TIME_INTERVAL = 0.20