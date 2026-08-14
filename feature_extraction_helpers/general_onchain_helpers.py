# TODO: comments: general API queries + retrieving block info

import time

import requests
from datetime import datetime, timezone

from feature_extraction_helpers.config import ETHERSCAN_TIME_INTERVAL, ETHERSCAN_API_KEY, CHAIN_IDS, ETHERSCAN_BASE_URL, \
    NODEREAL_TIME_INTERVAL, MEGANODE_BSC_URL, BLOCK_TIME_PERIODS


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
        if 'logs count exceeds the limit' in data['error'].get('message', ''):
            return 'LOG_LIMIT_EXCEEDED'
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
        print(f"No deployment transaction found for {token_address}")
        return None, None

    return data["blockNumber"], data["timestamp"]


# Get latest block number for a chain, used for Arbitrum tokens as the binary search upper bound
# https://docs.etherscan.io/api-reference/endpoint/ethblocknumber
def get_latest_block_eth(chain):
    data = query_etherscan(chain, {'module': 'proxy', 'action': 'eth_blockNumber'})
    if data is None:
        return None
    return int(data['result'], 16)


# Get latest block number and timestamp for all supported networks
def get_latest_block_with_timestamp(chain):
    if chain == 'BSC':
        # TODO: NodeReal implementation
        raise NotImplementedError()
    latest_block = get_latest_block_eth(chain)
    latest_block_timestamp = datetime.fromtimestamp(get_block_timestamp(chain, latest_block), tz=timezone.utc)
    return latest_block, latest_block_timestamp


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