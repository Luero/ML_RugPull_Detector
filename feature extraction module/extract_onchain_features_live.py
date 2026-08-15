# Extract features from any queried token on Eth, BSC, Arbitrum or Polygon using token contract address and blockchain
# Is used for feature extraction module of the application. Once extracted, features are submitted to the prediction module,
# where the developed model consume them to make a prediction

# To achieve consistency among features extracted per a single query, the last block at the time of query is used to get
# other features dependent on that information (not separate calls to retrieve the last block per feature, as blocks may
# appear during API calls execution.


# Features to extract (based on features list used by the model from the prediction module
#['MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)', '',
# 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# 'Google results for project x profile (duration/2)',
# 'has_contract_swap_patterns', 'has_owner_guard', ]


from datetime import datetime, timezone

import requests
import time

from feature_extraction_helpers.config import NETWORK_TO_BLOCKCHAIN_TYPE, MORALIS_CHAIN_IDS, MORALIS_BASE_URL, \
    MORALIS_API_KEY, BLOCKSCOUT_BASE_URLS, BLOCKSCOUT_MAX_RETRIES, BLOCKSCOUT_RETRY_DELAY_SECONDS
from feature_extraction_helpers.general_onchain_helpers import get_latest_block_eth, \
    get_deployment_block_and_timestamp, get_latest_block_with_timestamp
from feature_extraction_helpers.holders_count_helpers import get_holders_snapshots
from feature_extraction_helpers.general_onchain_helpers import query_etherscan


# Based on TM-RugPull methodology
LIVE_THRESHOLD_HOURS = 72

# Based on particular model trained on subset of features
TIME_FOR_SNAPSHOTS_HOURS = (12, 24)

# Get a timestamp of the latest token transaction to determine whether the queried token is live
# Reference: https://docs.etherscan.io/api-reference/endpoint/tokentx
def get_last_activity_timestamp(chain, token_address):
    if chain == 'BSC':
        # TODO: implement with NodeReal
        raise NotImplementedError()
    data = query_etherscan(chain, {
        'module': 'account', 'action': 'tokentx', 'contractaddress': token_address,
        'page': 1, 'offset': 1, 'sort': 'desc',
    })
    if data is None or not data.get('result'):
        return None
    return int(data['result'][0]['timeStamp'])


# Determine whether a token is live by checking the last activity timestamp
def is_token_live(last_activity_timestamp, latest_block_timestamp):
    if last_activity_timestamp is None:
        return False
    hours_since = (latest_block_timestamp - datetime.fromtimestamp(last_activity_timestamp, tz=timezone.utc)).total_seconds() / 3600
    return hours_since <= LIVE_THRESHOLD_HOURS


# Extract project period as required for prediction ('project period (days)')
def get_project_period_days(chain, token_address, deployment_block, deployment_timestamp, latest_block_timestamp):
    if deployment_block is None:
        print(f"No deployment block found for {token_address} on {chain}")
        return None
    print("Project period is calculating...")
    start_date = datetime.fromtimestamp(deployment_timestamp, tz=timezone.utc)
    last_activity_timestamp = get_last_activity_timestamp(chain, token_address)
    if is_token_live(last_activity_timestamp, latest_block_timestamp):
        end_date = latest_block_timestamp
    elif last_activity_timestamp is not None:
        end_date = datetime.fromtimestamp(last_activity_timestamp, tz=timezone.utc)
    else:
        # No activity ever
        return None

    return (end_date - start_date).days


# Extract 'Holders_12h', 'Holders_24h' features
def get_holders_count_snapshots(chain, token_address, time_for_snapshots_hour):
    print("Holders count snapshots are calculating...")
    latest_arbitrum_block = get_latest_block_eth('ARBI') if chain == 'ARBI' else None
    # Time for snapshots in hours that are used by the model
    snapshots = get_holders_snapshots(chain, token_address, time_for_snapshots_hour, latest_arbitrum_block)
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
        print(f"No Blockscout instance configured for {chain}")
        return None
    for attempt in range(1, BLOCKSCOUT_MAX_RETRIES + 1):
        try:
            response = requests.get(f"{base_url}/api/v2/tokens/{token_address}/counters", timeout=30)
        except requests.RequestException as e:
            print(f"Request error for {token_address} (attempt {attempt}/{BLOCKSCOUT_MAX_RETRIES}): {e}")
            if attempt < BLOCKSCOUT_MAX_RETRIES:
                time.sleep(BLOCKSCOUT_RETRY_DELAY_SECONDS)
                continue
            return None
        if response.status_code == 200:
            return response.json()
        print(f"HTTP {response.status_code} for {token_address} (attempt {attempt}/{BLOCKSCOUT_MAX_RETRIES}): {response.text}")
        if attempt < BLOCKSCOUT_MAX_RETRIES:
            time.sleep(BLOCKSCOUT_RETRY_DELAY_SECONDS)

    return None


# Extract 'the number of Transactions' feature, which appear to be transfer count for the token lifetime, based on TM-RugPull dataset
# For each supported chain except BSC uses Blockscout free API
# Reference: https://docs.blockscout.com/api-reference/smart-contracts/get-count-statistics-new-&-newly-verified-for-deployed-smart-contracts
def get_number_of_transactions(chain, token_address):
    print("Number of transactions are calculating...")
    if chain == 'BSC':
        # TODO: find a source for BSC
        raise NotImplementedError()
    counters = get_token_counters(chain, token_address)
    if counters is None:
        return None
    transfers_count = counters.get("transfers_count")
    if transfers_count is None:
        print(f"No transfers_count field for {token_address}")
        return None

    return int(transfers_count)


# Extract 'Token holder count' feature for all supported chains
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
        print(f"No token_holders_count field for {token_address}")
        return None

    return int(holders_count)


# Extract token holder count at the time of query for BSC tokens, uses Moralis free API with indexed number
# Reference: https://docs.moralis.com/data-api/evm/token/holders/token-holder-stats
# TODO: try to find frequency of indexing
# TODO: maybe use for Arbitrum, too (strange results from Blockscout)
def get_current_token_holder_count_bsc(token_address):
    moralis_chain = MORALIS_CHAIN_IDS.get('BSC')
    try:
        response = requests.get(
            f"{MORALIS_BASE_URL}/erc20/{token_address}/holders",
            params={"chain": moralis_chain},
            headers={"X-API-Key": MORALIS_API_KEY},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"Request error for {token_address}: {e}")
        return None
    if response.status_code != 200:
        print(f"HTTP {response.status_code} for {token_address}: {response.text}")
        return None
    data = response.json()
    total_holders = data.get("totalHolders")
    if total_holders is None:
        print(f"No totalHolders field for {token_address}")
        return None

    return int(total_holders)


def get_onchain_features_live(chain, token_address):
    # Used as 'now' point at time for  extracts values at the time of query and reuses them for all features to get them consistent in time
    latest_block, latest_block_timestamp = get_latest_block_with_timestamp(chain)
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, token_address)
    project_period_days = get_project_period_days(chain, token_address, deployment_block, deployment_timestamp, latest_block_timestamp)
    snapshots = get_holders_count_snapshots(chain, token_address, TIME_FOR_SNAPSHOTS_HOURS)
    blockchain_type = get_blockchain_type(chain)
    number_of_transactions = get_number_of_transactions(chain, token_address)
    current_token_holder_count = get_current_token_holder_count(chain, token_address)
    print("project_period_days:", project_period_days)
    print("snapshots:", snapshots)
    print("blockchain_type:", blockchain_type)
    print("number_of_transactions:", number_of_transactions)
    print("current_token_holder_count:", current_token_holder_count)




# TODO: a function for each feature + feeding features into the model


def main():
     get_onchain_features_live('ETH', '0x00f3C42833C3170159af4E92dbb451Fb3F708917')




if __name__ == "__main__":
    main()