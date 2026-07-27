# Extract block difference between token deployment block and pool creation block on relevant DEX.
# Etherscan APY key is required


import requests
from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook


# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_project_period.xlsx'
OUTPUT_FILE = '../data/TM-RugPull_with_difference_token_pull.xlsx'

# Sources of data
ETHSCAN_BASE_URL = 'https://api.etherscan.io/v2/api'
ETHERSCAN_API_KEY = 'YOUR_ETHERSCAN_API_KEY'
MEGANODE_BSC_URL = 'https://bsc-mainnet.nodereal.io/v1/YOUR_MEGANODE_API_KEY'

# IDs of chains supported by Etherscan and relevant for the dataset
# Reference: https://docs.etherscan.io/supported-chains
CHAIN_IDS = {'ETH': 1, 'POLYGON': 137, 'ARBI': 42161}







def main():




if __name__ == "__main__":
    main()