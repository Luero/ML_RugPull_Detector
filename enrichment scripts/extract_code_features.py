# Extract code-based features from source code files stored locally in .txt format (one file for each project from the
# dataset).
# .txt files are named according to row numbers in original version of the dataset.
# To map them with relevant projects, a composite key is used to avoid confusion, since the dataset has been cleaned from
# duplicate values.

# TODO: explain what features are extracted from the source code


from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook
import pandas as pd
import os
import re


# Original dataset file
ORIGINAL_FILE = '../data/TM-RugPull_original.xlsx'
# Local directory with contract code files
SOURCE_CODE_DIR = '../data/SOURCE CODE'

# Regex pattern to identify Solidity source code (for safety check run on all .txt files)
SOLIDITY_MARKER_PATTERN = re.compile(r'pragma\s+solidity|SPDX-License-Identifier|contract\s+\w', re.IGNORECASE)

# Rug-pull tokens usually mint entire or almost entire initial supply to a single address (usually deployer/owner's)
# Regex patterns are aimed to identify whether the contract allocates total supply to sender / owner address
# Reference: https://www.soliduslabs.com/post/rug-pull-crypto-scams
# Reference: https://dev.to/copyleftdev/cryptocurrency-rug-pull-scams-a-comprehensive-analysis-18ga
CONCENTRATED_MINT_PATTERNS = [
    re.compile(r'_mint\s*\(\s*(?:msg\.sender|owner|_owner)\s*,\s*(?:_totalSupply|totalSupply|TOTAL_SUPPLY)', re.IGNORECASE),
    re.compile(r'_balances\s*\[\s*(?:msg\.sender|owner|_owner)\s*\]\s*=\s*(?:_totalSupply|totalSupply|TOTAL_SUPPLY)', re.IGNORECASE),
    re.compile(r'balanceOf\s*\[\s*(?:msg\.sender|owner|_owner)\s*\]\s*=\s*(?:_totalSupply|totalSupply|TOTAL_SUPPLY)', re.IGNORECASE),
]

# Sometimes LP drain occurs via a swap rather than removal of liquidity
# The contract sells a large token balance for ETH/BNB to wallet controlled by owner, silently draining value from the pool
# Reference: https://www.certik.com/blog/the-vanishing-act-how-exit-scammers-mint-new-tokens-undetected
# All chins presented in dataset use the same interface and function name
# Reference: https://forum.openzeppelin.com/t/purpose-of-uniswap-pancake-factory-and-router-and-integration-in-openzeppelin/13369/5
SELF_SWAP_PATTERNS = [
    re.compile(r'swapExactTokensForETH\w*\s*\(', re.IGNORECASE),
    re.compile(r'swapTokensForEth\s*\(', re.IGNORECASE)
]

# Regex to check whether a swap call is restricted to owner
OWNER_GUARD_PATTERNS = [
    re.compile(r'onlyOwner', re.IGNORECASE),
    re.compile(r'require\s*\(\s*msg\.sender\s*==\s*(?:owner|_owner)\b', re.IGNORECASE),
]

# Unlocked liquidity may be one of signs of rug-pull, since there are no mechanisms preventing developer from withdrawal
# Absence of lock in contract does not mean liquidity is unlocked, external services may be used, but still worth checking
# Reference: https://simplebaseswap.com/blog/rug-pulls-explained-how-liquidity-scams-work/
LP_LOCK_REFERENCE_PATTERNS = [
    re.compile(r'\blockLiquidity\b', re.IGNORECASE),
    re.compile(r'\blockLP\b', re.IGNORECASE),
    re.compile(r'\bPinkLock\b', re.IGNORECASE),
    re.compile(r'\bTeamFinance\b', re.IGNORECASE),
    re.compile(r'\bUNCX\b', re.IGNORECASE),
    re.compile(r'\bunlockTime\b', re.IGNORECASE),
]

# Patterns for bytecode in .txt files (meaning that contract is not verified)
EVM_BYTECODE_PATTERN = re.compile(r'\b(?:PUSH\d*|JUMPDEST|MSTORE|SLOAD|SSTORE|REVERT)\b', re.IGNORECASE)

# Names for columns for enrichment
# 'Is_contract_verified' is added here for code simplicity, although it is not a sign of LP-drain,
# but could be a sign of scam in general. Extracted here, since the script checks .txt files to be bytecode
LP_DRAIN_FEATURE_NAMES = [
    'has_concentrated_initial_mint',
    'has_self_swap_patterns',
    'has_owner_guard',
    'has_lp_lock_reference',
    'is_contract_verified'
]

INPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'
OUTPUT_FILE = "../data/TM-RugPull_with_LP_drain_code_detection.xlsx"




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


# Build the path to files where contract code is located
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


# Check whether source code is bytecode, not a Solidity file
# If .txt file does not contain Solidity code, it is technically unfeasible in this script to extract necessary features,
# so their values will be treated as missing in enriched dataset
def is_bytecode(source_code):
    opcode_hits = len(EVM_BYTECODE_PATTERN.findall(source_code))
    return opcode_hits > 20                 # 20 is chosen to prevent accidential matches, it is unlikely to hit 20+ times


# Check whether full initial supply is assigned to a single address
# A precondition for control over liquidity, not a conclusive signal
def has_concentrated_initial_mint(source_code):
    return any(pattern.search(source_code) for pattern in CONCENTRATED_MINT_PATTERNS)


# Check whether contract defines a function that can swap its own token balance for ETH/BNB
# A precondition for removal (swapping) liquidity, not a conclusive signal
def has_self_swap_patterns(source_code):
    return any(pattern.search(source_code) for pattern in SELF_SWAP_PATTERNS)


# Check whether a swap call is restricted to owner
# Could be a strong signal in combination with has_self_swap_patterns
def has_owner_guard(source_code):
    return any(pattern.search(source_code) for pattern in OWNER_GUARD_PATTERNS)


# Check whether the source code contains any reference to a lock mechanism or known locker service
def has_lp_lock_reference(source_code):
    return any(pattern.search(source_code) for pattern in LP_LOCK_REFERENCE_PATTERNS)


# Compute features for a row in the dataset
def compute_lp_drain_features(row, mapping_result):
    source_code = load_source_code_for_row(row, mapping_result)
    status = check_source_file_safety(source_code)

    if check_source_file_safety(source_code) != 'OK':
        is_verified = 0 if status in ('EMPTY_FILE', 'UNVERIFIED_BYTECODE') else None
        return {'is_contract_verified': is_verified, **{name: None for name in LP_DRAIN_FEATURE_NAMES}}

    return {
        'is_contract_verified': 1,
        'has_concentrated_initial_mint': int(has_concentrated_initial_mint(source_code)),
        'has_self_swap_patterns': int(has_self_swap_patterns(source_code)),
        'has_owner_guard': int(has_owner_guard(source_code)),
        'has_lp_lock_reference': int(has_lp_lock_reference(source_code))
    }


# Add columns with potential LP-drain signals to the dataset
def add_lp_drain_feature_columns(sheet, headings, cleaned, mapping_result):
    first_new_col = len(headings) + 1
    for i, feature_name in enumerate(LP_DRAIN_FEATURE_NAMES):
        sheet.cell(row=1, column=first_new_col + i, value=feature_name)

    for i, row in cleaned.iterrows():
        excel_row = i + 2
        features = compute_lp_drain_features(row, mapping_result)
        for j, feature_name in enumerate(LP_DRAIN_FEATURE_NAMES):
            sheet.cell(row=excel_row, column=first_new_col + j, value=features[feature_name])


def main():
     original = pd.read_excel(ORIGINAL_FILE)
     cleaned = pd.read_excel(INPUT_FILE)
     mapping_result = map_key_to_original_row(original)
     workbook, sheet = load_file(INPUT_FILE)
     headings = get_headings(sheet)
     add_lp_drain_feature_columns(sheet, headings, cleaned, mapping_result)
     save_workbook(workbook, OUTPUT_FILE)

     # for i, row in cleaned.iterrows():
     #    match = resolve_source_file_number(row, mapping_result)
     #    print(f"{row['Project Title']} | {row['project end date']} --> source file: {match}.txt")



if __name__ == "__main__":
    main()