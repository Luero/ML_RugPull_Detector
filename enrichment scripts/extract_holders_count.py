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
import time

import requests
from dotenv import load_dotenv

from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook

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

# Time for snapshots in hours and approximation of average block time in seconds for each network
TIME_FOR_SNAPSHOTS_HOURS = (1, 4, 12, 24)

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
LATEST_ARBITRUM_BLOCK = None

# https://www.4byte.directory/event-signatures/?bytes_signature=0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef
TRANSFER_EVENT_HASH = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

# Etherscan free-tier limit on records per getLogs call: https://docs.etherscan.io/changelog
ETH_LOG_RESULT_LIMIT = 1000
# NodeReal limitations for block range size and number of records returned: https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
NODEREAL_LOG_RESULT_LIMIT = 50000
NODEREAL_BLOCK_RANGE_SIZE = 49000

# API limitations for calls per time
ETHERSCAN_TIME_INTERVAL = 0.35
NODEREAL_TIME_INTERVAL = 0.20

# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_project_period.xlsx'
OUTPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'


# General function to query Etherscan's endpoints
def query_etherscan(chain, params):
    time.sleep(ETHERSCAN_TIME_INTERVAL)
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
    time.sleep(NODEREAL_TIME_INTERVAL)
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
    had_failure = False

    if from_block > to_block:
        print(f"From_block ({from_block}) > to_block ({to_block})")
        return [], had_failure

    if chain != 'BSC':
        return get_transfer_logs_etherscan(chain, token_address, from_block, to_block)

    current_block = from_block
    while current_block <= to_block:
        chunk_end = min(current_block + NODEREAL_BLOCK_RANGE_SIZE, to_block)
        chunk_logs, chunk_failed = get_transfer_logs_bsc(token_address, current_block, chunk_end)
        all_logs.extend(chunk_logs)
        had_failure = had_failure or chunk_failed
        current_block = chunk_end + 1

    return all_logs, had_failure


# Get one chunk from Etherscan and use paginating if chunk hits LOG_RESULT_LIMIT
# https://docs.etherscan.io/changelog
def get_transfer_logs_etherscan(chain, token_address, from_block, to_block):
    chunk_logs = []
    page = 1
    while True:
        data = query_etherscan(chain, {
            'module': 'logs', 'action': 'getLogs',
            'address': token_address, 'topic0': TRANSFER_EVENT_HASH,
            'fromBlock': from_block, 'toBlock': to_block,
            'page': page, 'offset': ETH_LOG_RESULT_LIMIT
        })
        if data is None:
            return chunk_logs, True
        page_logs = data.get('result', [])
        chunk_logs.extend(page_logs)
        if len(page_logs) < ETH_LOG_RESULT_LIMIT:
            break
        page += 1

    return chunk_logs, False


# Get one chunk from NodeReal (for BSC tokens) considering API result limitations
# If limit is hit, function divides results and treats each half separately
# https://docs.nodereal.io/reference/eth-getlogs-bnb-chain
def get_transfer_logs_bsc(token_address, from_block, to_block):
    result = query_meganode('eth_getLogs', [{
        'address': token_address,
        'topics': [TRANSFER_EVENT_HASH],
        'fromBlock': hex(from_block),
        'toBlock': hex(to_block)
    }])

    if result is None:
        return [], True

    # Assumes NodeReal current limit of 50,000 records. If API changes, require revision
    if len(result) <= NODEREAL_LOG_RESULT_LIMIT or from_block == to_block:
        return result, False

    mid_block = (from_block + to_block) // 2
    left_logs, left_failure = get_transfer_logs_bsc(token_address, from_block, mid_block)
    right_logs, right_failure = get_transfer_logs_bsc(token_address, mid_block + 1, to_block)
    return left_logs + right_logs, left_failure or right_failure


# Extract a block number from log
def get_block_number_from_log(log):
    block_number = log['blockNumber']
    return int(block_number, 16) if isinstance(block_number, str) else int(block_number)


# Extract transfer value from log
# Assumes that contract defines Transfer event in compliance with ERC-20 standards, but accepts slight deviations
# If value cannot be extracted from logs, returns None and will be treated as missing value in the dataset later
def get_transfer_value_from_log(log):
    # Standard ERC-20 Transfer event
    if log['data'] != '0x':
        return int(log['data'], 16)
    # Non-standard Transfer event with indexed value
    # Added, since tests for some contract addresses (e.g. '0xF210D5d9DCF958803C286A6f8E278e4aC78e136E' on ETH) revealed
    # non-standard ERC-20 contract definition for Transfer event, thus, it needs to be handled
    if len(log['topics']) > 3:
        return int(log['topics'][-1], 16)
    print(f"Unsupported Transfer event format for {log['address']})")
    return None

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


# Replay transfers in block order up to each target_block and count addresses with positive balances
def count_holders_for_snapshots(logs, target_blocks):
    balances = {}
    snapshots = {}
    sorted_target_blocks = sorted(target_blocks.items(), key=lambda x: x[1])
    # Snapshot to look next
    current_target = 0

    # Replays all logs and stores snapshots on relevant time windows
    for log in logs:
        current_block = get_block_number_from_log(log)
        # Save a snapshot for a target block that was passed
        while current_target < len(sorted_target_blocks) and current_block > sorted_target_blocks[current_target][1]:
            snapshot_hours = sorted_target_blocks[current_target][0]
            snapshots[f"Holders_{snapshot_hours}h"] = sum(1 for balance in balances.values() if balance > 0)
            current_target += 1

        from_address = get_address_from_topic(log['topics'][1])
        to_address = get_address_from_topic(log['topics'][2])
        value = get_transfer_value_from_log(log)
        if value is None:
            print(f"Token {log['address']} skipped: unsupported Transfer event.")
            return None
        debit_from_address(balances, from_address, value)
        credit_to_address(balances, to_address, value)

    # Create snapshots if there were no mo transfers before next target snapshot
    while current_target < len(sorted_target_blocks):
        snapshot_hours = sorted_target_blocks[current_target][0]
        snapshots[f"Holders_{snapshot_hours}h"] = sum(1 for balance in balances.values() if balance > 0)
        current_target += 1

    return snapshots


# Per-token snapshot extraction
def get_holders_snapshots(chain, token_address):
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, token_address)
    if deployment_block is None:
        return {f"Holders_{h}h": math.nan for h in TIME_FOR_SNAPSHOTS_HOURS}            # https://www.w3schools.com/python/ref_math_nan.asp

    if chain == 'ARBI':
        global LATEST_ARBITRUM_BLOCK
        if LATEST_ARBITRUM_BLOCK is None:
            LATEST_ARBITRUM_BLOCK = get_latest_block(chain)
        # Blocks with timestamp closest to snapshots intervals
        target_blocks = {h: find_block_by_timestamp(chain, deployment_timestamp + h * 3600, deployment_block, LATEST_ARBITRUM_BLOCK) for h in TIME_FOR_SNAPSHOTS_HOURS}
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
    snapshots = count_holders_for_snapshots(logs, target_blocks)
    # If transfer value cannot be extracted from logs, holder counts for this token will be treated as missing value in dataset
    if snapshots is None:
        return {f'Holders_{h}h': math.nan for h in TIME_FOR_SNAPSHOTS_HOURS}

    return snapshots


# Save snapshots to an .xlxs file
def add_holder_snapshots_columns(sheet, headings):
    address_col_idx = headings.index('Contract address')
    chain_col_idx = headings.index('Blockchain')

    start_col = sheet.max_column + 1
    for i, h in enumerate(TIME_FOR_SNAPSHOTS_HOURS):
        sheet.cell(row=1, column=start_col + i, value=f"Holders_{h}h")

    for row in sheet.iter_rows(min_row=2):
        token_address = row[address_col_idx].value
        chain = row[chain_col_idx].value
        if not token_address or not chain:
            continue
        snapshots = get_holders_snapshots(chain, token_address)
        print(f"{token_address}: {snapshots}")
        for i, h in enumerate(TIME_FOR_SNAPSHOTS_HOURS):
            sheet.cell(row=row[0].row, column=start_col + i, value=snapshots.get(f"Holders_{h}h"))


def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)
    add_holder_snapshots_columns(sheet, headings)
    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()