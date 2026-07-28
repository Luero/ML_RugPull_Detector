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
    params['apikey'] = ETHERSCAN_API_KEY
    params['chainid'] = CHAIN_IDS[chain]
    response = requests.get(ETHERSCAN_BASE_URL, params=params, timeout=30)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {params.get('action')}")
        return None

    data = response.json()
    return data


# General function to query MegaNode endpoints
def query_meganode(method, params):
    payload = {'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}
    response = requests.post(MEGANODE_BSC_URL, json=payload, timeout=30)

    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for {method}")
        return None

    data = response.json()
    return data.get('result')


# Obtain deployment block number using token contract address
# https://docs.etherscan.io/api-reference/endpoint/getcontractcreation
def get_deployment_block_etherscan(chain, token_address):
    if chain == 'BSC':
        print("BSC requires a separate function")                 # A placeholder for a separate BSC related function

    data = query_etherscan(chain, {'module': 'contract', 'action': 'getcontractcreation', 'contractaddresses': token_address})

    if data is None or not data.get('result'):
        print(f"Could not get data for {token_address}")
        return None

    return int(data['result'][0]['blockNumber'])



def main():
    print(get_deployment_block_etherscan('ETH', '0xcbdcd3815b5f975e1a2c944a9b2cd1c985a1cb7f'))


if __name__ == "__main__":
    main()