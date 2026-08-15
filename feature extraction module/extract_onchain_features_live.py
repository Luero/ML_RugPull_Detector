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

from feature_extraction_helpers.config import NETWORK_TO_BLOCKCHAIN_TYPE, MORALIS_CHAIN_IDS, MORALIS_BASE_URL, \
    MORALIS_API_KEY
from feature_extraction_helpers.general_onchain_helpers import get_latest_block_eth, query_etherscan, \
    get_deployment_block_and_timestamp, get_latest_block_with_timestamp
from feature_extraction_helpers.holders_count_helpers import get_holders_snapshots, get_transfer_logs
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


# Extract number of transactions ('the number of Transactions') between deployment_block and latest_block
# Total number of on-chain token transfer transactions, as described in TM-RugPull methodology,is calculated with unique transactionHash values
# Uses
# TODO: check indexed API (try Moralis), since current logic is too slow for live queries. Other options: GoldRush
def get_number_of_transactions(chain, token_address, deployment_block, latest_block):
    print("Number of transactions are calculating...")
    if deployment_block is None:
        print(f"No deployment block found for {token_address} on {chain}")
        return None
    moralis_chain = MORALIS_CHAIN_IDS.get(chain)
    if moralis_chain is None:
        print(f"Unsupported chain {chain} for Moralis transfers endpoint")
        return None
    unique_tx_hashes = set()
    cursor = None
    while True:
        # Free plan allows only 100 results per page
        params = {"chain": moralis_chain, "from_block": int(deployment_block), "to_block": int(latest_block), "limit": 100}
        if cursor:
            params["cursor"] = cursor
        try:
            response = requests.get(
                f"{MORALIS_BASE_URL}/erc20/{token_address}/transfers",
                params=params,
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
        for transfer in data.get("result", []):
            unique_tx_hashes.add(transfer["transaction_hash"])
        cursor = data.get("cursor")
        if not cursor:
            break

    return len(unique_tx_hashes)


# Extract token holder count at the time of query or project end date (if is_token_live == False)
# TODO: Try Moralis API for current holders count and find how often it is indexed
def get_current_token_holder_count(chain, token_address):
    if chain == 'BSC':
        # TODO: implement for BSC
        raise NotImplementedError()


def get_onchain_features_live(chain, token_address):
    # Used as 'now' point at time for  extracts values at the time of query and reuses them for all features to get them consistent in time
    latest_block, latest_block_timestamp = get_latest_block_with_timestamp(chain)
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, token_address)
    project_period_days = get_project_period_days(chain, token_address, deployment_block, deployment_timestamp, latest_block_timestamp)
    snapshots = get_holders_count_snapshots(chain, token_address, TIME_FOR_SNAPSHOTS_HOURS)
    blockchain_type = get_blockchain_type(chain)
    number_of_transactions = get_number_of_transactions(chain, token_address, deployment_block, latest_block)
    print("project_period_days:", project_period_days)
    print("snapshots:", snapshots)
    print("blockchain_type:", blockchain_type)
    print("number_of_transactions:", number_of_transactions)




# TODO: a function for each feature + feeding features into the model


def main():
    get_onchain_features_live('ARBI', '0x25118290e6A5f4139381D072181157035864099d')



if __name__ == "__main__":
    main()