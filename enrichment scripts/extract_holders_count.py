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
CHAIN_IDS = {'ETH': 1, 'POLYGON': 137, 'ARBITRUM': 42161}


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
        print(f"API error: {data.get('message')}: {data.get('result')}")
        return None

    return data


# # General function to query MegaNode endpoints
# def query_meganode(method, params):
#     payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
#     response = requests.post(MEGANODE_BSC_URL, json=payload, timeout=30)
#
#     if response.status_code != 200:
#         print(f"HTTP error {response.status_code} for {method}")
#         return None
#
#     data = response.json()
#     if 'error' in data:
#         print(f"Error for {method}: {data['error']}")
#         return None
#
#     return data.get('result')


# Obtain deployment block number using token contract address
def get_deployment_block(chain, token_address):
    if chain == 'BSC':
        block_number = get_deployment_block_bsc(token_address)
    else:
        # https://docs.etherscan.io/api-reference/endpoint/getcontractcreation
        data = query_etherscan(chain, {'module': 'contract', 'action': 'getcontractcreation', 'contractaddresses': token_address})
        if data is None or not data.get('result'):
            print(f"Could not get data for {token_address}")
            return None
        block_number = int(data['result'][0]['blockNumber'])

    return block_number


# Obtain deployment block using token contract address for BSC tokens
# https://docs.nodereal.io/reference/nr_getcontractcreationtransaction
def get_deployment_block_bsc(token_address):
    payload = {'jsonrpc': '2.0', 'method': 'nr_getContractCreationTransaction', 'params': [token_address], 'id': 1}
    response = requests.post(MEGANODE_BSC_URL, json=payload, timeout=30)
    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {token_address}")
        return None

    result = response.json()
    if "error" in result:
        print(result["error"])
        return None

    data = result.get("result")
    if data is None:
        print("No result")
        return None

    return data["blockNumber"]


def main():
    print(get_deployment_block('BSC', '0xc297020be32dc91bb24ce4cad116eb50e55ec5ae'))


if __name__ == "__main__":
    main()