# Contains constants that are reused through feature extraction functions, including API keys and base URLs for
# data sources, source-specific chain ID resolutions, API limits, waiting intervals

import os
import re

from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

# Sources of data
# On-chain features, prices and contract code
# https://docs.etherscan.io/api-reference
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
ETHERSCAN_BASE_URL = 'https://api.etherscan.io/v2/api'
# https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
NODEREAL_API_KEY = os.getenv('NODEREAL_API_KEY')
MEGANODE_BSC_URL = f'https://bsc-mainnet.nodereal.io/v1/{NODEREAL_API_KEY}'
# https://docs.moralis.com/data-api/evm/token/holders/token-holder-stats
MORALIS_BASE_URL = "https://deep-index.moralis.io/api/v2.2"
MORALIS_API_KEY = os.getenv('MORALIS_API_KEY')
# https://docs.blockscout.com/api-reference/smart-contracts/get-count-statistics-new-&-newly-verified-for-deployed-smart-contracts
BLOCKSCOUT_BASE_URLS = {
    "ETH": "https://eth.blockscout.com",
    "ARBI": "https://arbitrum.blockscout.com",
    "POLYGON": "https://polygon.blockscout.com",
}
# Used for prices extraction, no historical limit, but only daily prices available
# Reference: https://defillama.com/docs/api
DEFILLAMA_BASE_URL = 'https://coins.llama.fi'
# Maximum number of daily points per /chart call (found empirically)
DEFILLAMA_MAX_SPAN = 500

# Off-chain features
# https://serpapi.com/search-api
SERP_API_KEY = os.getenv('SERP_API_KEY')
SERP_BASE_URL = "https://serpapi.com/search?engine=google"
# https://docs.dexscreener.com/api/reference (is used to get website URL and X profile based on token address)
DEXSCREENER_BASE_URL = "https://api.dexscreener.com"

# https://docs.coingecko.com/docs/keyless-public-api
COINGECKO_API_KEY= os.getenv('COINGECKO_API_KEY')
COINGECKO_BASE_URL = 'https://api.coingecko.com/api/v3'
# https://docs.coingecko.com/docs/keyless-public-api
GECKOTERMINAL_BASE_URL = 'https://api.coingecko.com/api/v3/onchain'


# A guard for rejecting calls for API where a lot of information is retrieved
ETHERSCAN_MAX_RETRIES = 3
ETHERSCAN_RETRY_DELAY_SECONDS = 1.0
# Sometimes server return code 500 (internal server error), so 3 retries per call is set
BLOCKSCOUT_MAX_RETRIES = 3
BLOCKSCOUT_RETRY_DELAY_SECONDS = 1.5
# Same logic
GECKOTERMINAL_MAX_RETRIES = 3
GECKOTERMINAL_RETRY_DELAY_SECONDS = 2.0
# Same logic
MORALIS_MAX_RETRIES = 3
MORALIS_RETRY_DELAY_SECONDS = 1.0

# IDs of chains supported by Etherscan and relevant for the dataset
# Reference: https://docs.etherscan.io/supported-chains
ETHERSCAN_CHAIN_IDS = {'ETH': 1, 'POLYGON': 137, 'ARBI': 42161, 'BSC': 56}


# IDs of chains supported by Moralis
# Reference: https://docs.moralis.com/data-api/evm/token/transfers/token-transfers
MORALIS_CHAIN_IDS = {"ETH": "0x1", "BSC": "0x38", "POLYGON": "0x89", "ARBI": "0xa4b1"}


# IDs of chains supported by CoinGecko and CoinGeckoTerminal
# Reference: https://docs.coingecko.com/demo/reference/asset-platforms-list
COINGECKO_CHAIN_IDS = {'ETH': 'ethereum', 'BSC': 'binance-smart-chain', 'POLYGON': 'polygon-pos', 'ARBI': 'arbitrum-one'}
# Reference: https://docs.coingecko.com/demo/reference/networks-list
GECKOTERMINAL_NETWORK_IDS = {'ETH': 'eth', 'BSC': 'bsc', 'POLYGON': 'polygon_pos', 'ARBI': 'arbitrum'}

# IDs of chains suppported by DEXScreener
DEXSCREENER_CHAIN_IDS = {'ETH': 'ethereum', 'BSC': 'bsc', 'POLYGON': 'polygon', 'ARBI': 'arbitrum'}

# IDs of chains supported by DeFiLama
DEFILLAMA_CHAIN_IDS = {'ETH': 'ethereum', 'BSC': 'bsc', 'POLYGON': 'polygon', 'ARBI': 'arbitrum'}

# Historical data available only for 180 days in the past for demo API key
GECKOTERMINAL_MAX_DEPTH_SECONDS = 180 * 24 * 3600

# https://www.4byte.directory/event-signatures/?bytes_signature=0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
TRANSFER_EVENT_HASH = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


# Etherscan free-tier limit on records per getLogs call: https://docs.etherscan.io/changelog
ETH_LOG_RESULT_LIMIT = 1000
# NodeReal limitations for block range size and number of records returned: https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
NODEREAL_BLOCK_RANGE_SIZE = 49000
# toBlock - fromBlock must be less than 2000000 (searched empirically with nr_getAssetTransfersCount call)
NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE = 1999999


# API limitations for calls per time
ETHERSCAN_TIME_INTERVAL = 0.45              # 3 calls/sec, but here is a conservative number to keep a margin
NODEREAL_TIME_INTERVAL = 0.20
# Reference: https://docs.coingecko.com/docs/keyless-public-api
COINGECKO_TIME_INTERVAL = 0.65
GECKOTERMINAL_TIME_INTERVAL = 2.1
# Depends on CU (computing units)
MORALIS_TIME_INTERVAL = 0.15
# No hard published limit, but small interval used to be safe
DEFILLAMA_TIME_INTERVAL = 0.15


# Mapping between blockchain and consensus type
NETWORK_TO_BLOCKCHAIN_TYPE = {'ETH': 'POS', 'BSC': 'POSA', 'ARBI': 'Fraud Proofs', 'POLYGON': 'POS'}


# Since BSC is not covered by Etherscan free plan, approximate block time periods are used:
# before April 2025 - 3.01 sec, then reduced after forks (mean calculated based on official Bscscan data: https://bscscan.com/chart/blocktime)
# Starting date is not real BSC genesis date, just a placeholder for 'very early date'
BLOCK_TIME_PERIODS_BSC = {
    'BSC': (
        (datetime(2000, 4, 20, tzinfo=timezone.utc), datetime(2025, 4, 29, tzinfo=timezone.utc), 3.01),
        (datetime(2025, 4, 29, tzinfo=timezone.utc), datetime(2025, 6, 30, tzinfo=timezone.utc), 1.50),
        (datetime(2025, 6, 30, tzinfo=timezone.utc), datetime(2026, 1, 14, tzinfo=timezone.utc), 0.75),
        (datetime(2026, 1, 14, tzinfo=timezone.utc), datetime(2100, 1, 1, tzinfo=timezone.utc), 0.45),
    )
}

# EVM contract address format: '0x' followed by 40 hexadecimal characters
CONTRACT_ADDRESS_PATTERN = re.compile(r'^0x[a-fA-F0-9]{40}$')
