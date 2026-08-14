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
# (6) adds relevant columns with number of holders on a particular time to .xlxs file

# Etherscan API key is required for Ethereum, Arbitrum and Polygon tokens
# MegaNode API key is required for BSC tokens (since Etherscan free plan does not support it) (https://docs.etherscan.io/supported-chains)


from feature_extraction_helpers.holders_count_helpers import get_holders_snapshots
from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook
from feature_extraction_helpers.general_onchain_helpers import get_latest_block


# Time for snapshots in hours
TIME_FOR_SNAPSHOTS_HOURS = (1, 4, 12, 24)

# Files to read and write
INPUT_FILE = '../research/data/TM-RugPull_with_project_period.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_holder_count_snapshots.xlsx' was used in original experiment
OUTPUT_FILE = "../research/data/placeholder.xlsx"


# Save snapshots to an .xlxs file
def add_holder_snapshots_columns(sheet, headings):
    address_col_idx = headings.index('Contract address')
    chain_col_idx = headings.index('Blockchain')

    start_col = sheet.max_column + 1
    for i, h in enumerate(TIME_FOR_SNAPSHOTS_HOURS):
        sheet.cell(row=1, column=start_col + i, value=f"Holders_{h}h")

    latest_arbitrum_block = get_latest_block('ARBI')

    for row in sheet.iter_rows(min_row=2):
        token_address = row[address_col_idx].value
        chain = row[chain_col_idx].value
        if not token_address or not chain:
            continue
        snapshots = get_holders_snapshots(chain, token_address, TIME_FOR_SNAPSHOTS_HOURS, latest_arbitrum_block)
        print(f"{token_address}: {snapshots}")
        for i, h in enumerate(TIME_FOR_SNAPSHOTS_HOURS):
            sheet.cell(row=row[0].row, column=start_col + i, value=snapshots.get(f"Holders_{h}h"))


def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)
    add_holder_snapshots_columns(sheet, headings)
    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()