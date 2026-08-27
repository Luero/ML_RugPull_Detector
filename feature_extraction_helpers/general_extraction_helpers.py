# Contains general helpers to extract features from different sources:
# (1) general source-specific functions to construct relevant queries;
# (2) general block-related functions to retrieve relevant blocks, their timestamps and other metadata;

# Sources used:
# - Etherscan
# - MegaNode (NodeReal)
# - CoinGecko
# - CoinGeckoTerminal
# - Moralis
# - DEXScreener
# - DeFiLama

import time

import requests
from datetime import datetime, timezone

from feature_extraction_helpers.config import ETHERSCAN_TIME_INTERVAL, ETHERSCAN_API_KEY, ETHERSCAN_CHAIN_IDS, \
    ETHERSCAN_BASE_URL, NODEREAL_TIME_INTERVAL, MEGANODE_BSC_URL, BLOCK_TIME_PERIODS_BSC, COINGECKO_BASE_URL, \
    COINGECKO_TIME_INTERVAL, \
    COINGECKO_API_KEY, GECKOTERMINAL_TIME_INTERVAL, GECKOTERMINAL_BASE_URL, MORALIS_TIME_INTERVAL, MORALIS_API_KEY, \
    MORALIS_BASE_URL, NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE, DEXSCREENER_BASE_URL, ETHERSCAN_MAX_RETRIES, \
    ETHERSCAN_RETRY_DELAY_SECONDS, GECKOTERMINAL_MAX_RETRIES, GECKOTERMINAL_RETRY_DELAY_SECONDS, MORALIS_MAX_RETRIES, \
    MORALIS_RETRY_DELAY_SECONDS, DEFILLAMA_TIME_INTERVAL, DEFILLAMA_BASE_URL

# Based on TM-RugPull methodology
LIVE_THRESHOLD_HOURS = 72

# One shared HTTP session to make API calls more efficient
SESSION = requests.Session()

# Timestamps of last call per provider, to sleep only the remaining part
LAST_CALL_TIMES = {}


# Ensure minimal interval between calls to one provider, count time spent since previous call
def wait_for_rate_limit(provider, time_interval):
    last_call_time = LAST_CALL_TIMES.get(provider)
    if last_call_time is not None:
        elapsed = time.monotonic() - last_call_time
        if elapsed < time_interval:
            time.sleep(time_interval - elapsed)
    LAST_CALL_TIMES[provider] = time.monotonic()


# General function to query Etherscan's endpoints
def query_etherscan(chain, params):
    data_not_found_messages = {'No records found', 'No data found', 'No transactions found'}
    params = params.copy()
    params['apikey'] = ETHERSCAN_API_KEY
    params['chainid'] = ETHERSCAN_CHAIN_IDS[chain]
    for attempt in range(1, ETHERSCAN_MAX_RETRIES + 1):
        wait_for_rate_limit('etherscan', ETHERSCAN_TIME_INTERVAL)
        try:
            response = SESSION.get(ETHERSCAN_BASE_URL, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"...Request error for {params.get('action')}: {e}")
            return None
        if response.status_code != 200:
            print(f"...HTTP error {response.status_code} for {params.get('action')}")
            return None
        data = response.json()
        # If per-second limit still hit the call is retried after a pause
        if data.get('message') == 'NOTOK' and 'rate limit' in str(data.get('result', '')).lower():
            if attempt < ETHERSCAN_MAX_RETRIES:
                print(
                    f"...Etherscan rate limit hit for {params.get('action')} (attempt {attempt}/{ETHERSCAN_MAX_RETRIES}), retrying...")
                time.sleep(ETHERSCAN_RETRY_DELAY_SECONDS)
                continue
            print(f"...Etherscan rate limit reached for {params.get('action')}")
            return None
        if params.get('module') == 'proxy':
            if 'error' in data:
                print(f"...Proxy API error: {data['error']}")
                return None
            return data
        if data.get('status') not in ('1', 1):
            # A valid empty result
            if data.get('message') in data_not_found_messages:
                return data
            print(f"...API error: {data.get('message')}: {data.get('result')}")
            return None
        return data
    return None


# General function to query MegaNode endpoints
def query_meganode(method, params):
    wait_for_rate_limit('nodereal', NODEREAL_TIME_INTERVAL)
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    try:
        response = SESSION.post(MEGANODE_BSC_URL, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"...Request error for {method}: {e}")
        return None
    if response.status_code != 200:
        print(f"...HTTP error {response.status_code} for {method}")
        return None
    data = response.json()
    if 'error' in data:
        if 'logs count exceeds the limit' in data['error'].get('message', ''):
            return 'LOG_LIMIT_EXCEEDED'
        print(f"...Error for {method}: {data['error']}")
        return None
    return data.get('result')


# General function to query CoinGecko's public endpoints
# Reference: https://docs.coingecko.com/docs/keyless-public-api
def query_coingecko(endpoint, params=None):
    wait_for_rate_limit('coingecko', COINGECKO_TIME_INTERVAL)
    headers = {'x-cg-demo-api-key': COINGECKO_API_KEY}
    try:
        response = SESSION.get(f"{COINGECKO_BASE_URL}{endpoint}", params=params or {}, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"...Request error for {endpoint}: {e}")
        return None
    if response.status_code == 404:
        print(f"...CoinGecko has no tracked coin for {endpoint}")
        return None
    if response.status_code != 200:
        print(f"...HTTP error {response.status_code} for {endpoint}")
        return None
    return response.json()


# General function to query GeckoTerminal's public endpoints
# Reference: https://docs.coingecko.com/docs/keyless-public-api
def query_geckoterminal(endpoint, params=None):
    headers = {'x-cg-demo-api-key': COINGECKO_API_KEY}
    for attempt in range(1, GECKOTERMINAL_MAX_RETRIES + 1):
        wait_for_rate_limit('geckoterminal', GECKOTERMINAL_TIME_INTERVAL)
        try:
            response = SESSION.get(f"{GECKOTERMINAL_BASE_URL}{endpoint}", params=params or {}, headers=headers, timeout=30)
        except requests.RequestException as e:
            print(f"...Request error for {endpoint}: {e}")
            return None
        if response.status_code == 200:
            return response.json()
        # Error body may be non-JSON, so raw text is printed (confirmed empirically)
        print(f"...HTTP error {response.status_code} for {endpoint} (attempt {attempt}/{GECKOTERMINAL_MAX_RETRIES}): {response.text[:200]}")
        if response.status_code in (429, 500, 502, 503, 504) and attempt < GECKOTERMINAL_MAX_RETRIES:
            time.sleep(GECKOTERMINAL_RETRY_DELAY_SECONDS)
            continue
        return None
    return None


# General function to query Moralis's endpoints
# https://docs.moralis.com/data-api/evm/token/overview
def query_moralis(endpoint, params=None):
    headers = {'X-API-Key': MORALIS_API_KEY}
    for attempt in range(1, MORALIS_MAX_RETRIES + 1):
        wait_for_rate_limit('moralis', MORALIS_TIME_INTERVAL)
        try:
            response = SESSION.get(f"{MORALIS_BASE_URL}{endpoint}", params=params or {}, headers=headers, timeout=30)
        except requests.RequestException as e:
            print(f"...Request error for {endpoint}: {e}")
            return None
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            print(f"...Moralis has no data for {endpoint}")
            return None
        # Error body may be non-JSON, so raw text is printed
        print(f"...HTTP error {response.status_code} for {endpoint} (attempt {attempt}/{MORALIS_MAX_RETRIES}): {response.text[:200]}")
        if response.status_code in (429, 500, 502, 503, 504) and attempt < MORALIS_MAX_RETRIES:
            time.sleep(MORALIS_RETRY_DELAY_SECONDS)
            continue
        return None
    return None


# General function to query DEXScreener's public endpoints
# Reference: https://docs.dexscreener.com/api/reference
def query_dexscreener(endpoint):
    try:
        response = SESSION.get(f"{DEXSCREENER_BASE_URL}{endpoint}", timeout=30)
    except requests.RequestException as e:
        print(f"...Request error for DEXScreener endpoint {endpoint}: {e}")
        return None
    if response.status_code != 200:
        print(f"...HTTP error {response.status_code} for DEXScreener endpoint {endpoint}")
        return None
    return response.json()


# General function to query DeFiLlama's public price API
# Reference: https://defillama.com/docs/api
def query_defillama(endpoint, params=None):
    wait_for_rate_limit('defillama', DEFILLAMA_TIME_INTERVAL)
    try:
        response = SESSION.get(f"{DEFILLAMA_BASE_URL}{endpoint}", params=params or {}, timeout=30)
    except requests.RequestException as e:
        print(f"...Request error for DeFiLlama endpoint {endpoint}: {e}")
        return None
    if response.status_code != 200:
        print(f"...HTTP error {response.status_code} for DeFiLlama endpoint {endpoint}: {response.text[:200]}")
        return None
    return response.json()


# Obtain deployment block number using token contract address
def get_deployment_block_and_timestamp(chain, token_address):
    if chain == 'BSC':
        return get_deployment_block_and_timestamp_bsc(token_address)
    else:
        # https://docs.etherscan.io/api-reference/endpoint/getcontractcreation
        data = query_etherscan(chain, {'module': 'contract', 'action': 'getcontractcreation', 'contractaddresses': token_address})
        if data is None or not data.get('result'):
            print(f"...Could not get data for {token_address}")
            return None, None
        result = data['result'][0]
        return int(result['blockNumber']), int(result['timestamp'])


# Obtain deployment block using token contract address for BSC tokens
# https://docs.nodereal.io/reference/nr_getcontractcreationtransaction
def get_deployment_block_and_timestamp_bsc(token_address):
    wait_for_rate_limit('nodereal', NODEREAL_TIME_INTERVAL)
    payload = {'jsonrpc': '2.0', 'method': 'nr_getContractCreationTransaction', 'params': [token_address], 'id': 1}
    try:
        response = SESSION.post(MEGANODE_BSC_URL, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"Request error for {token_address}: {e}")
        return None, None
    if response.status_code != 200:
        print(f"...HTTP error {response.status_code} for {token_address}")
        return None, None
    result = response.json()
    if "error" in result:
        print(result["error"])
        return None, None
    data = result.get("result")
    if data is None:
        print(f"...No deployment transaction found for {token_address}")
        return None, None
    return data["blockNumber"], data["timestamp"]


# Get latest block number for a chain, used for Arbitrum tokens as the binary search upper bound
# https://docs.etherscan.io/api-reference/endpoint/ethblocknumber
def get_latest_block_eth(chain):
    data = query_etherscan(chain, {'module': 'proxy', 'action': 'eth_blockNumber'})
    if data is None:
        return None
    return int(data['result'], 16)


# Get a block's timestamp via Etherscan
# https://docs.etherscan.io/api-reference/endpoint/ethgetblockbynumber
def get_block_timestamp(chain, block_number):
    data = query_etherscan(chain, {'module': 'proxy', 'action': 'eth_getBlockByNumber', 'tag': hex(block_number), 'boolean': 'false'})
    if data is None:
        return None
    return int(data['result']['timestamp'], 16)


# Get latest block number for BSC via NodeReal
# https://docs.nodereal.io/reference/eth-blocknumber-bnb-chain
def get_latest_block_meganode():
    result = query_meganode('eth_blockNumber', [])
    if result is None:
        return None
    return int(result, 16)


# Get a block's timestamp via NodeReal
# https://docs.nodereal.io/reference/eth-getblockbynumber-bnb-chain
def get_block_timestamp_meganode(block_number):
    result = query_meganode('eth_getBlockByNumber', [hex(block_number), False])
    if result is None:
        return None
    return int(result['timestamp'], 16)


# Get latest block number and timestamp for all supported networks
def get_latest_block_with_timestamp(chain):
    if chain == 'BSC':
        latest_block = get_latest_block_meganode()
        if latest_block is None:
            return None, None
        latest_block_timestamp = get_block_timestamp_meganode(latest_block)
        if latest_block_timestamp is None:
            return None, None
        return latest_block, datetime.fromtimestamp(latest_block_timestamp, tz=timezone.utc)
    latest_block = get_latest_block_eth(chain)
    if latest_block is None:
        return None, None
    latest_block_timestamp = get_block_timestamp(chain, latest_block)
    if latest_block_timestamp is None:
        return None, None
    return latest_block, datetime.fromtimestamp(latest_block_timestamp, tz=timezone.utc)


# Get the number of block closest to a target timestamp.
# Reference: https://docs.etherscan.io/api-reference/endpoint/getblocknobytime
def get_block_number_by_timestamp(chain, target_timestamp):
    data = query_etherscan(chain, {'module': 'block', 'action': 'getblocknobytime', 'timestamp': int(target_timestamp), 'closest': 'before'})
    if data is None:
        return None
    result = data.get('result')
    # Etherscan can respond with error string instead of number (revealed while testing)
    if not str(result).isdigit():
        print(f"...No block number resolved for timestamp {int(target_timestamp)}: {result}")
        return None
    return int(result)


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


# Extract block time for the token's deployment timestamp
def get_block_time_seconds(chain, deployment_timestamp):
    deployment_datetime = datetime.fromtimestamp(int(deployment_timestamp), tz=timezone.utc)
    for start, end, block_time in BLOCK_TIME_PERIODS_BSC[chain]:
        if start <= deployment_datetime < end:
            return block_time
    return None


# Convert time window in hours into an approximate number of blocks for a particular chain
def hours_to_blocks(chain, hours, deployment_timestamp):
    block_time = get_block_time_seconds(chain, deployment_timestamp)
    if block_time is None:
        return None
    return int((hours * 3600) / block_time)


# Get a timestamp of the latest token transaction to determine whether the queried token is live
# Reference: https://docs.etherscan.io/api-reference/endpoint/tokentx
def get_last_activity_timestamp(chain, token_address, latest_block, deployment_block):
    if chain == 'BSC':
        return get_last_activity_timestamp_bsc(token_address, latest_block, deployment_block)
    data = query_etherscan(chain, {
        'module': 'account', 'action': 'tokentx', 'contractaddress': token_address,
        'page': 1, 'offset': 1, 'sort': 'desc',
    })
    if data is None or not data.get('result'):
        return None
    return int(data['result'][0]['timeStamp'])


# Get a timestamp of the lates token transfer event for BSC tokens
def get_last_activity_timestamp_bsc(token_address, latest_block, deployment_block):
    if latest_block is None or deployment_block is None:
        return None
    to_block = latest_block
    while to_block >= deployment_block:
        from_block = max(deployment_block, to_block - NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE)
        result = query_meganode('nr_getAssetTransfers', [{
            'category': ['20'],
            'contractAddresses': [token_address],
            'fromBlock': hex(from_block),
            'toBlock': hex(to_block),
            'order': 'desc',
            'maxCount': '0x1',
        }])
        if result is None:
            return None
        transfers = result.get('transfers', [])
        if transfers:
            return transfers[0]['blockTimeStamp']
        if from_block == deployment_block:
            break
        to_block = from_block - 1
    return None


# Determine whether a token is live by checking the last activity timestamp
def is_token_live(last_activity_timestamp, latest_block_timestamp):
    if last_activity_timestamp is None:
        return False
    hours_since = (latest_block_timestamp - datetime.fromtimestamp(last_activity_timestamp, tz=timezone.utc)).total_seconds() / 3600
    return hours_since <= LIVE_THRESHOLD_HOURS