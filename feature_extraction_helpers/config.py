# TODO: general comment

import os

from dotenv import load_dotenv
from datetime import datetime, timezone

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


# TODO: extend to reuse for current tokens
# For ETH: before September 2022 - 14.52 sec, after - 12.07 sec (mean calculated based on official Etherscan data: https://etherscan.io/chart/blocktime)
# For BSC: before April 2025 - 3.01 sec (mean calculated based on official Bscscan data: https://bscscan.com/chart/blocktime)
# For Polygon: before May 2026 - 2.17 sec (mean calculated based on official Polygonscan data: https://polygonscan.com/chart/blocktime)
# For Arbitrum: no fixed block time, it depends on demand, thus, approximation could spoil results (https://docs.arbitrum.io/arbitrum-essentials/arbitrum-vs-ethereum/block-numbers-and-time)
# Starting dates are not real chains' genesis dates, just a placeholder for 'very early date'
BLOCK_TIME_PERIODS = {
    'ETH': (
        (datetime(2000, 7, 30, tzinfo=timezone.utc), datetime(2022, 9, 15, tzinfo=timezone.utc), 14.52),
        (datetime(2022, 9, 15, tzinfo=timezone.utc), datetime(2100, 1, 1, tzinfo=timezone.utc), 12.07),
    ),
    'BSC': (
        (datetime(2000, 4, 20, tzinfo=timezone.utc), datetime(2025, 4, 1, tzinfo=timezone.utc), 3.01),
    ),
    'POLYGON': (
        (datetime(2000, 5, 30, tzinfo=timezone.utc), datetime(2026, 5, 5, tzinfo=timezone.utc), 2.17),
    ),
}
