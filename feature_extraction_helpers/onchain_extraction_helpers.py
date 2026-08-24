# Extract features from any queried token on Eth, BSC, Arbitrum or Polygon using token contract address and blockchain.
# Is used for feature_extraction_module of the application. Once extracted, features are submitted to the prediction module,
# where the developed model consume them to make a prediction.


from datetime import datetime, timezone

import requests
import time
import math

from feature_extraction_helpers.config import NETWORK_TO_BLOCKCHAIN_TYPE, MORALIS_CHAIN_IDS, BLOCKSCOUT_BASE_URLS, BLOCKSCOUT_MAX_RETRIES, BLOCKSCOUT_RETRY_DELAY_SECONDS, \
    NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE
from feature_extraction_helpers.general_extraction_helpers import is_token_live, query_moralis, query_meganode, SESSION
from feature_extraction_helpers.holders_count_helpers import get_holders_snapshots


# Based on particular model trained on subset of features
TIME_FOR_SNAPSHOTS_HOURS = (12, 24)


# Extract project period as required for prediction ('project period (days)')
def get_project_period_days(chain, token_address, deployment_block, deployment_timestamp, latest_block_timestamp, last_activity_timestamp):
    if deployment_block is None:
        print(f"...No deployment block found for {token_address} on {chain}")
        return None
    print("Project period is calculating...")
    start_date = datetime.fromtimestamp(deployment_timestamp, tz=timezone.utc)
    if is_token_live(last_activity_timestamp, latest_block_timestamp):
        end_date = latest_block_timestamp
    elif last_activity_timestamp is not None:
        end_date = datetime.fromtimestamp(last_activity_timestamp, tz=timezone.utc)
    else:
        # No activity ever
        return None
    return (end_date - start_date).days


# Extract 'Holders_12h', 'Holders_24h' features
def get_holders_count_snapshots(chain, token_address, time_for_snapshots_hour, deployment_block, deployment_timestamp, latest_block_timestamp):
    print("Holders count snapshots are calculating...")
    # Checks that a token is not younger than a snapshot window
    elapsed_hours = (latest_block_timestamp - datetime.fromtimestamp(deployment_timestamp, tz=timezone.utc)).total_seconds() / 3600
    # Time for snapshots in hours that are used by the model
    valid_hours = tuple(h for h in time_for_snapshots_hour if h <= elapsed_hours)
    snapshots = {f"Holders_{h}h": math.nan for h in time_for_snapshots_hour}
    if valid_hours:
        snapshots.update(get_holders_snapshots(chain, token_address, valid_hours, deployment_block, deployment_timestamp))
    else:
        print(f"...Token {token_address} is younger than any snapshot window")
    return snapshots


# Extract 'Blockchain Type' (then encode with pre-fitted and saved OneHotEncoder and leave what the model consumes)
def get_blockchain_type(chain):
    print("Blockchain type is calculating...")
    return NETWORK_TO_BLOCKCHAIN_TYPE[chain]


# General function to retrieve indexed number of transfers and holder count via Blockscout API (/counters endpoint)
# Works for all supported chains except BSC
def get_token_counters(chain, token_address):
    base_url = BLOCKSCOUT_BASE_URLS.get(chain)
    if base_url is None:
        print(f"...No Blockscout instance configured for {chain}")
        return None
    for attempt in range(1, BLOCKSCOUT_MAX_RETRIES + 1):
        try:
            response = SESSION.get(f"{base_url}/api/v2/tokens/{token_address}/counters", timeout=30)
        except requests.RequestException as e:
            print(f"...Request error for {token_address} (attempt {attempt}/{BLOCKSCOUT_MAX_RETRIES}): {e}")
            if attempt < BLOCKSCOUT_MAX_RETRIES:
                time.sleep(BLOCKSCOUT_RETRY_DELAY_SECONDS)
                continue
            return None
        if response.status_code == 200:
            return response.json()
        print(f"...HTTP {response.status_code} for {token_address} (attempt {attempt}/{BLOCKSCOUT_MAX_RETRIES}): {response.text}")
        if attempt < BLOCKSCOUT_MAX_RETRIES:
            time.sleep(BLOCKSCOUT_RETRY_DELAY_SECONDS)
    return None


# Extract 'the number of Transactions' feature, which appear to be transfer count for the token lifetime, based on TM-RugPull dataset
# For each supported chain except BSC uses Blockscout free API
# Reference: https://docs.blockscout.com/api-reference/smart-contracts/get-count-statistics-new-&-newly-verified-for-deployed-smart-contracts
def get_number_of_transactions(chain, token_address, deployment_block, latest_block):
    print("Number of transactions are calculating...")
    if chain == 'BSC':
        return get_number_of_transactions_bsc(token_address, deployment_block, latest_block)
    counters = get_token_counters(chain, token_address)
    if counters is None:
        return None
    transfers_count = counters.get("transfers_count")
    if transfers_count is None:
        print(f"...No transfers_count field for {token_address}")
        return None
    return int(transfers_count)


# Extract the number of transactions for BSC from NodeReal
# Reference: https://docs.nodereal.io/reference/nr_getassettransferscount
def get_number_of_transactions_bsc(token_address, deployment_block, latest_block):
    if deployment_block is None or latest_block is None:
        return None
    total_transfers = 0
    from_block = deployment_block
    while from_block <= latest_block:
        to_block = min(latest_block, from_block + NODEREAL_ASSET_TRANSFERS_BLOCK_RANGE)
        result = query_meganode('nr_getAssetTransfersCount', [{
            'category': ['20'],
            'contractAddresses': [token_address],
            'fromBlock': hex(from_block),
            'toBlock': hex(to_block),
        }])
        if result is None:
            print(f"...Failed to get transfer count for {token_address} in block range {from_block}-{to_block}")
            return None
        total_transfers += int(result, 16)
        from_block = to_block + 1
    return total_transfers


# Extract 'Number of holders' feature for all supported chains
# For all chains except BSC uses Blockscout cached results
def get_current_token_holder_count(chain, token_address):
    print("Current token holders number is calculating...")
    if chain == 'BSC':
        return get_current_token_holder_count_bsc(token_address)
    counters = get_token_counters(chain, token_address)
    if counters is None:
        return None
    holders_count = counters.get("token_holders_count")
    if holders_count is None:
        print(f"...No token_holders_count field for {token_address}")
        return None
    return int(holders_count)


# Extract token holder count ('Number of holders') at the time of query for BSC tokens, uses Moralis free API with indexed number
# Reference: https://docs.moralis.com/data-api/evm/token/holders/token-holder-stats
def get_current_token_holder_count_bsc(token_address):
    moralis_chain = MORALIS_CHAIN_IDS.get('BSC')
    data = query_moralis(f"/erc20/{token_address}/holders", {"chain": moralis_chain})
    if data is None:
        print(f"...No holder data for {token_address}")
        return None
    total_holders = data.get("totalHolders")
    if total_holders is None:
        print(f"...No totalHolders field for {token_address}")
        return None
    return int(total_holders)


def get_onchain_features_live(chain, token_address, deployment_block, deployment_timestamp, latest_block, latest_block_timestamp, last_activity_timestamp):
    project_period_days = get_project_period_days(chain, token_address, deployment_block, deployment_timestamp, latest_block_timestamp, last_activity_timestamp)
    snapshots = get_holders_count_snapshots(chain, token_address, TIME_FOR_SNAPSHOTS_HOURS, deployment_block, deployment_timestamp, latest_block_timestamp)
    blockchain_type = get_blockchain_type(chain)
    number_of_transactions = get_number_of_transactions(chain, token_address, deployment_block, latest_block)
    current_token_holder_count = get_current_token_holder_count(chain, token_address)
    features = {
        'project period (days)': project_period_days,
        'the number of Transactions': number_of_transactions,
        'Number of holders': current_token_holder_count,
        'Blockchain Type': blockchain_type,
    }
    features.update(snapshots)
    return features