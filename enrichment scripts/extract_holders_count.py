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
# (6) adds relevant columns with number of holders on a particular time to .xlxs file

# Etherscan API key is required for Ethereum, Arbitrum and Polygon tokens
# MegaNode API key is required for BSC tokens (since Etherscan free plan does not support it) (https://docs.etherscan.io/supported-chains)


import os
from datetime import datetime, timezone
import math

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
    data_not_found_messages = {'No records found', 'No data found', 'No transactions found'}
    params = params.copy()
    params['apikey'] = ETHERSCAN_API_KEY
    params['chainid'] = CHAIN_IDS[chain]
    response = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=30)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {params.get('action')}")
        return None

    data = response.json()

    if params.get('module') == 'proxy':
        if 'error' in data:
            print(f"Proxy API error: {data['error']}")
            return None
        return data

    if data.get('status') not in ('1', 1):
        # A valid empty result, not an error, in holders count will be treated as 0 holders
        if data.get('message') in data_not_found_messages:
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


# Get latest block number for a chain, used for Arbitrum tokens as the binary search upper bound
# https://docs.etherscan.io/api-reference/endpoint/ethblocknumber
def get_latest_block(chain):
    data = query_etherscan(chain, {'module': 'proxy', 'action': 'eth_blockNumber'})
    if data is None:
        return None
    return int(data['result'], 16)


# Binary search for Arbitrum tokens: search for block closest to to_timestamp
def find_block_by_timestamp(chain, to_timestamp, low_block, high_block):
    closest_block = low_block

    while low_block <= high_block:
        mid_block = (low_block + high_block) // 2
        mid_timestamp = get_block_timestamp(chain, mid_block)
        if mid_timestamp is None:
            break
        if mid_timestamp <= to_timestamp:
            closest_block = mid_block
            low_block = mid_block + 1
        else:
            high_block = mid_block - 1

    return closest_block


# Get a block's timestamp via Etherscan
# https://docs.etherscan.io/api-reference/endpoint/ethgetblockbynumber
def get_block_timestamp(chain, block_number):
    data = query_etherscan(chain, {'module': 'proxy', 'action': 'eth_getBlockByNumber', 'tag': hex(block_number), 'boolean': 'false'})
    if data is None:
        return None
    return int(data['result']['timestamp'], 16)


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
    had_failure = False

    if from_block > to_block:
        print(f"From_block ({from_block}) > to_block ({to_block})")
        return [], had_failure

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
            if result is None:
                had_failure = True
            else:
                all_logs.extend(result)
        else:
            data = query_etherscan(chain, {
                'module': 'logs', 'action': 'getLogs',
                'address': token_address, 'topic0': TRANSFER_EVENT_HASH,
                'fromBlock': current_block, 'toBlock': chunk_end
            })
            if data is None:
                had_failure = True
            else:
                all_logs.extend(data.get('result', []))

        current_block = chunk_end + 1

    return all_logs, had_failure


# Extract a block number from log
def get_block_number_from_log(log):
    block_number = log['blockNumber']
    return int(block_number, 16) if isinstance(block_number, str) else int(block_number)


# Extract transfer value from log
def get_transfer_value_from_log(log):
    return int(log['data'], 16)


# Extract address from topic value
def get_address_from_topic(topic):
    return '0x' + topic[-40:]


# Replay debit transactions from address
def debit_from_address(balances, address, value):
    balances[address] = balances.get(address, 0) - value


# Replay credit transactions from address
# Raw values are left-padded, with zeros upfront, since they are 32-bytes, and addresses are only 20 bytes
def credit_to_address(balances, address, value):
    balances[address] = balances.get(address, 0) + value


# Replay transfers in block order up to target_block and count addresses with positive balances
def count_holders_to_target_block(logs, to_block):
    balances = {}

    for log in logs:
        if get_block_number_from_log(log) > to_block:
            break

        from_address = get_address_from_topic(log['topics'][1])
        to_address = get_address_from_topic(log['topics'][2])
        value = get_transfer_value_from_log(log)

        debit_from_address(balances, from_address, value)
        credit_to_address(balances, to_address, value)

    return sum(1 for balance in balances.values() if balance > 0)


# Per-token snapshot extraction
def get_holders_snapshots(chain, token_address):
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, token_address)
    if deployment_block is None:
        return {f"Holders_{h}h": math.nan for h in TIME_FOR_SNAPSHOTS_HOURS}            # https://www.w3schools.com/python/ref_math_nan.asp

    if chain == 'ARBITRUM':
        latest_block = get_latest_block(chain)
        # Blocks with timestamp closest to snapshots intervals
        target_blocks = {h: find_block_by_timestamp(chain, deployment_timestamp + h * 3600, deployment_block, latest_block) for h in TIME_FOR_SNAPSHOTS_HOURS}
    else:
        # Approximate number of blocks for each snapshot interval
        block_offsets = {h: hours_to_blocks(chain, h, deployment_timestamp) for h in TIME_FOR_SNAPSHOTS_HOURS}
        # Blocks calculated from deployment block + offset relevant for a particular chain
        target_blocks = {h: deployment_block + offset for h, offset in block_offsets.items() if offset is not None}

    # Upper boundary for getting and replaying logs
    max_block = max(target_blocks.values())
    logs, had_failure = get_transfer_logs(chain, token_address, int(deployment_block), max_block)
    if had_failure:
        print(f"Log failure for {token_address}")
        return {f"Holders_{h}h": math.nan for h in TIME_FOR_SNAPSHOTS_HOURS}
    logs.sort(key=get_block_number_from_log)
    snapshots = {}
    for h in TIME_FOR_SNAPSHOTS_HOURS:
        to_block = target_blocks.get(h)
        snapshots[f"Holders_{h}h"] = count_holders_to_target_block(logs, to_block)

    return snapshots


def main():
    snapshots = get_holders_snapshots('ARBITRUM', '0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a')
    print(snapshots)



if __name__ == "__main__":
    main()