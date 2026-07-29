# Extract holder count snapshots (number of distinct holders at fixed time intervals after deployment) using contract address.
# Return snapshots for 1 hour, 4 hours, 12 hours and 24 hours, since most rug-pulls live within 1 day and the best time-window
# to detect them is within first 8-20 hours (see Report).
#
# The script performs the following steps:
# (1) finds the deployment block and obtains the block number
# (2) converts each time window into a block offset using each chain's average block time (a necessary approximation explained in the Report)
# (3) extracts all transfer events between deployment and snapshot blocks (the last snapshot block is used to fetch logs only once and then use them from memory)
# (4) replays transfers in order, maintains a running balance per address and takes a snapshot debit_from_addr(), credit_to_addr()
# (5) counts addresses with positive remaining balances

# TODO: check my theory works in practice

# Etherscan API key is required for Ethereum, Arbitrum and Polygon tokens
# MegaNode API key is required for BSC tokens (since Etherscan free plan does not support it)


import os
from datetime import datetime, timezone

import requests
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
# TODO: Arbitrum???
CHAIN_IDS = {'ETH': 1, 'POLYGON': 137, 'ARBITRUM': 42161}

# Time for snapshots in hours and approximation of average block time in seconds for each network
TIME_FOR_SNAPSHOTS_HOURS = (1, 4, 12, 24)

# For ETH: before September 2022 - 14.52 sec, after - 12.07 sec (mean calculated based on official Etherscan data: https://etherscan.io/chart/blocktime)
# For BSC: before April 2025 - 3.01 sec (mean calculated based on official Bscscan data: https://bscscan.com/chart/blocktime)
# For Polygon: before May 2026 - 2.17 sec (mean calculated based on official Polygonscan data: https://polygonscan.com/chart/blocktime)
# For Arbitrum: no fixed block time, it depends on demand, thus, approximation could spoil results (https://docs.arbitrum.io/arbitrum-essentials/arbitrum-vs-ethereum/block-numbers-and-time)
# TODO: try binary search for blocks lookup ??
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

# https://www.4byte.directory/event-signatures/?bytes_signature=0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
TRANSFER_EVENT_HASH = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
# Unified across all chains, suits for the smallest available chunk (ETH)
LOG_BLOCK_CHUNK_SIZE = 1000
# Etherscan free-tier limit on records per getLogs call
LOG_RESULT_LIMIT = 1000


# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_project_period.xlsx'
OUTPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'


# General function to query Etherscan's endpoints
def query_etherscan(chain, params):
    params = params.copy()
    params['apikey'] = ETHERSCAN_API_KEY
    params['chainid'] = CHAIN_IDS[chain]
    response = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=30)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {params.get('action')}")
        return None

    data = response.json()
    if data.get('status') not in ('1', 1):
        # A valid empty result, not an error, in holders count will be treated as 0 holders
        if data.get('message') == 'No records found':
            return data
        print(f"API error: {data.get('message')}: {data.get('result')}")
        return None

    return data


# General function to query MegaNode endpoints
def query_meganode(method, params):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    response = requests.post(MEGANODE_BSC_URL, json=payload, timeout=30)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {method}")
        return None

    data = response.json()
    if 'error' in data:
        print(f"Error for {method}: {data['error']}")
        return None

    return data.get('result')


# Obtain deployment block number using token contract address
def get_deployment_block_and_timestamp(chain, token_address):
    if chain == 'BSC':
        return get_deployment_block_and_timestamp_bsc(token_address)
    else:
        # https://docs.etherscan.io/api-reference/endpoint/getcontractcreation
        data = query_etherscan(chain, {'module': 'contract', 'action': 'getcontractcreation', 'contractaddresses': token_address})
        if data is None or not data.get('result'):
            print(f"Could not get data for {token_address}")
            return None, None
        result = data['result'][0]

        return int(result['blockNumber']), int(result['timestamp'])


# Obtain deployment block using token contract address for BSC tokens
# https://docs.nodereal.io/reference/nr_getcontractcreationtransaction
def get_deployment_block_and_timestamp_bsc(token_address):
    payload = {'jsonrpc': '2.0', 'method': 'nr_getContractCreationTransaction', 'params': [token_address], 'id': 1}
    response = requests.post(MEGANODE_BSC_URL, json=payload, timeout=30)
    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {token_address}")
        return None, None

    result = response.json()
    if "error" in result:
        print(result["error"])
        return None, None

    data = result.get("result")
    if data is None:
        print("No result")
        return None, None

    return data["blockNumber"], data["timestamp"]


# Extract block time for the token's deployment timestamp
def get_block_time_seconds(chain, deployment_timestamp):
    deployment_datetime = datetime.fromtimestamp(int(deployment_timestamp), tz=timezone.utc)
    for start, end, block_time in BLOCK_TIME_PERIODS[chain]:
        if start <= deployment_datetime < end:
            return block_time
    return None


# Convert time window in hours into an approximate number of blocks for a particular chain
def hours_to_blocks(chain, hours, deployment_timestamp):
    block_time = get_block_time_seconds(chain, deployment_timestamp)
    if block_time is None:
        return None
    return int((hours * 3600) / block_time)


# Extract all transfer event logs between from_block and to_block, chunked due to API limits
def get_transfer_logs(chain, token_address, from_block, to_block):
    all_logs = []
    current_block = from_block

    if from_block > to_block:
        print(f"From_block ({from_block}) > to_block ({to_block})")
        return []

    while current_block <= to_block:
        chunk_end = min(current_block + LOG_BLOCK_CHUNK_SIZE, to_block)

        if chain == 'BSC':
            # https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
            result = query_meganode('eth_getLogs', [{
                'address': token_address,
                'topics': [TRANSFER_EVENT_HASH],
                'fromBlock': hex(current_block),
                'toBlock': hex(chunk_end)
            }])
            all_logs.extend(result if result else [])
        else:
            data = query_etherscan(chain, {
                'module': 'logs', 'action': 'getLogs',
                'address': token_address, 'topic0': TRANSFER_EVENT_HASH,
                'fromBlock': current_block, 'toBlock': chunk_end
            })
            all_logs.extend(data.get('result', []) if data else [])

        current_block = chunk_end + 1
    print(all_logs)

    return all_logs


def main():
    from_block, timestamp = get_deployment_block_and_timestamp('ETH', '0x6daa2195d0a67c23b4976bd388736c56e71c3f39')
    print(from_block, timestamp)
    block_offset = hours_to_blocks('ETH', 1, timestamp)
    to_block = from_block + block_offset
    get_transfer_logs('ETH', '0x6daa2195d0a67c23b4976bd388736c56e71c3f39', from_block, to_block)


if __name__ == "__main__":
    main()