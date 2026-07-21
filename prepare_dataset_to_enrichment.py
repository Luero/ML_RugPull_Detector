# Prepare dataset in .xlsx file for enrichment:
# - remove chains with small amount of samples (based on initial analysis)
# - extract contract address for further enrichment with on-chain features
# - check dataset for identical rows by contract address

# OpenPyXL is used here to preserve hyperlinks in the file.
# All actions with .xlsx are based on initial analysis (see Jupyter notebook "TM-RugPull initial analysis").
# They are grouped here for convenience (to edit .xlxs file once and save results to a new ready-to-go file)

# Reference: https://openpyxl.readthedocs.io/en/3.1/tutorial.html

from openpyxl import load_workbook
import re


# Load .xlsx file using OpenPyXL
# Returns workbook and sheet from .xlcx file
def load_file (file):
    workbook = load_workbook(file)
    sheet = workbook['Sheet1']
    return workbook, sheet


# Drop rows where 'Blockchain' column contains value for networks that were excluded from further analysis
def drop_chains(sheet, headings, chains_to_drop):
    blockchain_column_idx = headings.index('Blockchain')
    rows_to_drop = [row[0].row for row in sheet.iter_rows(min_row=2) if row[blockchain_column_idx].value in chains_to_drop]

    for row_num in sorted(rows_to_drop, reverse=True):
        sheet.delete_rows(row_num, 1)

    # Check how many rows remain (should be 990 for TM-RugPull dataset)
    print(sheet.max_row - 1, "rows remaining")


# Add contract addresses to all remaining rows in the file for further extraction of on-chain features
# Addresses are extracted from hyperlinks from 'Smart Contract (online)' column
# Reference: https://docs.python.org/3/library/re.html
def add_contract_addresses(sheet, headings):
    contract_link_column_idx = headings.index('Smart Contract (online)')
    address_column_number = len(headings) + 1

    # A regex pattern for contract address that is used to extract addresses from URLs
    # Compiled once for efficiency
    address_pattern = re.compile(r'0x[a-fA-F0-9]{40}')

    sheet.cell(row=1, column=address_column_number, value='Contract address')

    for row in sheet.iter_rows(min_row=2):
        cell = row[contract_link_column_idx]
        if cell.hyperlink is None:
            print(f"Row {cell.row}: no hyperlink")
            continue
        # Reference: https://openpyxl.readthedocs.io/en/3.1/api/openpyxl.worksheet.hyperlink.html
        match = address_pattern.search(cell.hyperlink.target)
        if match is None:
            print(f"Row {cell.row}: could not extract address")
            continue
        address = match.group(0).lower()
        sheet.cell(row=cell.row, column=address_column_number, value=address)


# Save a workbook with amenmdnments to a new .xlxs file
def save_workbook(workbook, output_file):
    workbook.save(output_file)


# Combine all actions with a file together
def main():
    workbook, sheet = load_file("data/TM-RugPull.xlsx")
    headings = [c.value for c in sheet[1]]
    # Based on initial analysis
    chains_to_drop = {'FANTOM', 'CRONO', 'BASE', 'FTM', 'SNOW'}
    drop_chains(sheet, headings, chains_to_drop)
    add_contract_addresses(sheet, headings)
#    save_workbook(workbook, 'data/TM-RugPull_filtered_chains.xlsx')


if __name__ == "__main__":
    main()
