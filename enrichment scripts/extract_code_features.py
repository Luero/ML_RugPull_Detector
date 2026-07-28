# Extract block difference between token deployment block and pool creation block on relevant DEX.
# Etherscan APY key is required


import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Sources of data
ETHERSCAN_API_KEY = os.getenv('ETHERSCAN_API_KEY')
ETHERSCAN_BASE_URL = 'https://api.etherscan.io/v2/api'
NODEREAL_API_KEY = os.getenv('NODEREAL_API_KEY')
MEGANODE_BSC_URL = 'https://bsc-mainnet.nodereal.io/v1/' + NODEREAL_API_KEY


# IDs of chains supported by Etherscan and relevant for the dataset
# Reference: https://docs.etherscan.io/supported-chains
CHAIN_IDS = {'ETH': 1, 'POLYGON': 137, 'ARBI': 42161}


# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_project_period.xlsx'
OUTPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'







def main():
    print()


if __name__ == "__main__":
    main()