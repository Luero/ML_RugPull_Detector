# Extract holder count snapshots (number of distinct holders at fixed time intervals after deployment) using contract address.
# Etherscan API key is required for Ethereum, Arbitrum and Polygon tokens
# MegaNode API key is required for BSC tokens (since Etherscan free plan does not support it)


import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Sources of data
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
ETHERSCAN_BASE_URL = 'https://api.etherscan.io/v2/api'
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




def main():
    # https://docs.etherscan.io/api-reference/endpoint/ethblocknumber
    print(query_etherscan('ETH', {'module': 'proxy', 'action': 'eth_blockNumber'}))


if __name__ == "__main__":
    main()