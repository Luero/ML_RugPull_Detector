# Helper functions to extract holder count snapshots
# Used both for the dataset enrichment and for live feature extraction pipeline

import math

from feature_extraction_helpers.config import NODEREAL_BLOCK_RANGE_SIZE, ETH_LOG_RESULT_LIMIT, TRANSFER_EVENT_HASH
from feature_extraction_helpers.general_extraction_helpers import query_etherscan, query_meganode, \
    get_deployment_block_and_timestamp, find_block_by_timestamp, hours_to_blocks


# Extract all transfer event logs between from_block and to_block, chunked due to API limits
def get_transfer_logs(chain, token_address, from_block, to_block):
    all_logs = []
    had_failure = False

    if from_block > to_block:
        print(f"...From_block ({from_block}) > to_block ({to_block})")
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


# Etherscan-specific function to retrieve transfer logs
def get_transfer_logs_etherscan(chain, token_address, from_block, to_block):
    chunk_logs = []
    page = 1
    while True:
        # Etherscan allows up to page * offset <= 10000
        if page * ETH_LOG_RESULT_LIMIT > 10000:
            # Prevents infinite recursion
            if from_block == to_block:
                print(f"...Too many logs in block {from_block} for {token_address}")
                return chunk_logs, True
            mid_block = (from_block + to_block) // 2
            left_logs, left_failure = get_transfer_logs_etherscan(chain, token_address, from_block, mid_block)
            right_logs, right_failure = get_transfer_logs_etherscan(chain, token_address, mid_block + 1, to_block)
            return left_logs + right_logs, left_failure or right_failure

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


# Retrieve transfer logs for BSC tokens using NodeReal API
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
    # Handles situation when number of logs returned exceeds API limit (50000)
    if result == 'LOG_LIMIT_EXCEEDED':
        if from_block == to_block:
            print(f"...Too many logs in block {from_block} for {token_address}")
            return [], True
        mid_block = (from_block + to_block) // 2
        left_logs, left_failure = get_transfer_logs_bsc(token_address, from_block, mid_block)
        right_logs, right_failure = get_transfer_logs_bsc(token_address, mid_block + 1, to_block)
        return left_logs + right_logs, left_failure or right_failure

    return result, False


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
    print(f"...Unsupported Transfer event format for {log['address']})")
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
            print(f"...Token {log['address']} skipped: unsupported Transfer event")
            return None
        debit_from_address(balances, from_address, value)
        credit_to_address(balances, to_address, value)

    # Create snapshots if there were no more transfers before next target snapshot
    while current_target < len(sorted_target_blocks):
        snapshot_hours = sorted_target_blocks[current_target][0]
        snapshots[f"Holders_{snapshot_hours}h"] = sum(1 for balance in balances.values() if balance > 0)
        current_target += 1

    return snapshots


# Per-token snapshot extraction
def get_holders_snapshots(chain, token_address, time_for_snapshot_hours, latest_arbitrum_block=None, deployment_block=None, deployment_timestamp=None):
    if deployment_block is None:
        deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, token_address)
    if deployment_block is None:
        return {f"Holders_{h}h": math.nan for h in time_for_snapshot_hours}

    if chain == 'ARBI':
        # Blocks with timestamp closest to snapshots intervals
        target_blocks = {h: find_block_by_timestamp(chain, deployment_timestamp + h * 3600, deployment_block, latest_arbitrum_block) for h in time_for_snapshot_hours}
    else:
        # Approximate number of blocks for each snapshot interval
        block_offsets = {h: hours_to_blocks(chain, h, deployment_timestamp) for h in time_for_snapshot_hours}
        # Blocks calculated from deployment block + offset relevant for a particular chain
        target_blocks = {h: deployment_block + offset for h, offset in block_offsets.items() if offset is not None}

    # Upper boundary for getting and replaying logs
    max_block = max(target_blocks.values())
    logs, had_failure = get_transfer_logs(chain, token_address, int(deployment_block), max_block)
    if had_failure:
        print(f"...Log failure for {token_address}")
        return {f"Holders_{h}h": math.nan for h in time_for_snapshot_hours}
    logs.sort(key=get_block_number_from_log)
    snapshots = count_holders_for_snapshots(logs, target_blocks)
    # If transfer value cannot be extracted from logs, holder counts for this token will be treated as missing value in dataset
    if snapshots is None:
        return {f'Holders_{h}h': math.nan for h in time_for_snapshot_hours}

    return snapshots