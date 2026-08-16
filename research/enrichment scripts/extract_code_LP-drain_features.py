# Extract code-based features from source code files stored locally in .txt format (one file for each project from the
# dataset).
# .txt files are named according to row numbers in original version of the dataset.
# To map them with relevant projects, a composite key is used to avoid confusion, since the dataset has been cleaned from
# duplicate values.

# The script extracts the following features aimed to detect common implementations of potential liquidity drain signals,
# a main way of executing rug-pulls:
# (1) 'has_consentrated_initial_mint' - checks whether initial token distribution is concentrated on one address (developer/owner)
# (2) 'has_self_swap_patterns'- checks whether a contract pre-defines possibility to swap all tokens for base cryptocurrency
# (3) 'has_owner_guard' - checks whether swaps could be performed only by the project's owner
# (4) 'has_lp_lock_reference'- checks whether liquidity is locked by the contract or referenced to any external lock sources
# All these signals by their own are not evidence of LP-drain, but using in combination to train ML model they may become
# predictive.

# The script also extracts 'is_contract_verified' feature. It does not relate to LP-drain specifically, but it is extracted here,
# since unverified contracts could be a general signal of scam, including rug-pulls, and during extraction of LP-specific features
# it turns out that some .txt files contain bytecode, meaning that contracts are not verified. Thus, to preserve this information
# rather than loosing it, the feature also was added into the dataset.


from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook
import pandas as pd
import os

from feature_extraction_helpers.source_code_helplers import SOLIDITY_MARKER_PATTERN, is_bytecode, \
    LP_DRAIN_FEATURE_NAMES, has_concentrated_initial_mint, has_contract_swap_patterns, has_owner_guard, \
    has_lp_lock_reference, ALL_FEATURE_NAMES


# Original dataset file
ORIGINAL_FILE = '../data/TM-RugPull_original.xlsx'
# Local directory with contract code files
SOURCE_CODE_DIR = '../data/SOURCE CODE'

INPUT_FILE = '../research/data/TM-RugPull_with_holder_count_snapshots.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_LP_drain_code_detection.xlsx' was used in original experiment
OUTPUT_FILE = "../research/data/placeholder.xlsx"


# Build a composite key to use for mapping projects to relevant rows in original dataset and then to .txt files
# Using simple a project title could fail, because there are projects with identical names
# Uses values for 'Project Title' and 'project end date'
def build_composite_key(row):
    return f"{row['Project Title']}|{row['project end date']}"


# Map each composite key in original file to its row number.
def map_key_to_original_row(original):
    result = {}
    for i, row in original.iterrows():
        key = build_composite_key(row)
        excel_row_number = i + 2              # 1 row in .xlxs is a heading, pandas indexing is from 0
        result.setdefault(key, []).append(excel_row_number)
    return result


# Resolve rows of current version of the dataset to its original file number
def resolve_source_file_number(row, mapping_result):
    key = build_composite_key(row)
    matches = mapping_result.get(key)
    if not matches:
        print(f"No original row match for: {row['Project Title']}")
        return None
    if len(matches) > 1:
        print(f"Ambiguous match for {row['Project Title']}: candidates {matches}")
        return None
    return matches[0]


# Source files are stored under their original dataset row numbers, so the path should be built to them using mapping
def build_path_to_source_code_file(original_row_number):
    filename = f"{original_row_number}.txt"
    return os.path.join(SOURCE_CODE_DIR, filename)


# Load source code .txt file for a particular row using row number and mapping result
def load_source_code_for_row(row, mapping_result):
    file_number = resolve_source_file_number(row, mapping_result)
    if file_number is None:
        return None
    path = build_path_to_source_code_file(file_number)
    if not os.path.isfile(path):
        print(f"Source file missing: {path}")
        return None
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as code_file:
            return code_file.read()
    except OSError as e:
        print(f"Could not read {path}: {e}")
        return None


# Check whether a file is present, not empty and looks like Solidity source code file
# Required to avoid errors and false positive results by running feature extraction on files that are not source codes
def check_source_file_safety(source_code):
    if source_code is None:
        return 'MISSING_FILE'
    if len(source_code.strip()) < 10:
        return 'EMPTY_FILE'
    if is_bytecode(source_code):
        return 'UNVERIFIED_BYTECODE'
    if not SOLIDITY_MARKER_PATTERN.search(source_code):
        return 'NOT_SOLIDITY'
    return 'OK'


# Compute features for a row in the dataset
def compute_lp_drain_features(row, mapping_result):
    source_code = load_source_code_for_row(row, mapping_result)
    status = check_source_file_safety(source_code)

    if status != 'OK':
        is_verified = 0 if status in ('EMPTY_FILE', 'UNVERIFIED_BYTECODE') else None
        features = {name: None for name in LP_DRAIN_FEATURE_NAMES}
        features["is_contract_verified"] = is_verified
        return features

    return {
        'is_contract_verified': 1,
        'has_concentrated_initial_mint': int(has_concentrated_initial_mint(source_code)),
        'has_contract_swap_patterns': int(has_contract_swap_patterns(source_code)),
        'has_owner_guard': int(has_owner_guard(source_code)),
        'has_lp_lock_reference': int(has_lp_lock_reference(source_code))
    }


# Add columns with potential LP-drain signals to the dataset
def add_lp_drain_feature_columns(sheet, headings, cleaned, mapping_result):
    first_new_col = len(headings) + 1
    for i, feature_name in enumerate(ALL_FEATURE_NAMES):
        sheet.cell(row=1, column=first_new_col + i, value=feature_name)

    for i, row in cleaned.iterrows():
        excel_row = i + 2
        features = compute_lp_drain_features(row, mapping_result)
        for j, feature_name in enumerate(ALL_FEATURE_NAMES):
            sheet.cell(row=excel_row, column=first_new_col + j, value=features[feature_name])


def main():
     original = pd.read_excel(ORIGINAL_FILE)
     cleaned = pd.read_excel(INPUT_FILE)
     mapping_result = map_key_to_original_row(original)
     workbook, sheet = load_file(INPUT_FILE)
     headings = get_headings(sheet)
     add_lp_drain_feature_columns(sheet, headings, cleaned, mapping_result)
     save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()