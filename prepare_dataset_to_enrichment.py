# Prepare dataset in .xlsx file for enrichment:
# - remove chains with small amount of samples (based on initial analysis)
# - extract contract address for further enrichment with on-chain features
# - check dataset for identical rows by contract address

# OpenPyXL is used here to preserve hyperlinks in the file

# Reference: https://openpyxl.readthedocs.io/en/3.1/tutorial.html

from openpyxl import load_workbook


# Load .xlsx file using OpenPyXL
# Returns workbook and sheet from .xlcx file
def load_file (file):
    workbook = load_workbook(file)
    sheet = workbook['Sheet1']
    return workbook, sheet


# Drop rows where 'Blockchain' column contains value for networks that were excluded from further analysis
def drop_chains(sheet, chains_to_drop):
    headings = [c.value for c in sheet[1]]
    chain_column_idx = headings.index('Blockchain')
    rows_to_drop = [row[0].row for row in sheet.iter_rows(min_row=2) if row[chain_column_idx].value in chains_to_drop]

    for row_num in sorted(rows_to_drop, reverse=True):
        sheet.delete_rows(row_num, 1)

    # Check how many rows remain (should be 990 for TM-RugPull dataset)
    print(sheet.max_row - 1, "rows remaining")


# Save a workbook with amenmdnments to a new .xlxs file
def save_workbook(workbook, output_file):
    workbook.save(output_file)


if __name__ == "__main__":
    workbook, sheet = load_file("data/TM-RugPull.xlsx")
    chains_to_drop = {'FANTOM', 'CRONO', 'BASE', 'FTM', 'SNOW'}
    drop_chains(sheet, chains_to_drop)
#    save_workbook(workbook, 'data/TM-RugPull_filtered_chains.xlsx')