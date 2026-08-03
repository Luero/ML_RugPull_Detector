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
import re


# Original dataset file
ORIGINAL_FILE = '../data/TM-RugPull_original.xlsx'
# Local directory with contract code files
SOURCE_CODE_DIR = '../data/SOURCE CODE'

# Regex pattern to identify Solidity source code (for safety check run on all .txt files)
SOLIDITY_MARKER_PATTERN = re.compile(r'pragma\s+solidity|SPDX-License-Identifier|contract\s+\w', re.IGNORECASE)

# Rug-pull tokens usually mint entire or almost entire initial supply to a single address (usually deployer/owner's)
# Regex patterns are aimed to identify common code patterns when the contract allocates total supply to specific address
# Not malicious on its own, but could be a signal in combination with other features
# Reference: https://www.soliduslabs.com/post/rug-pull-crypto-scams
# Reference: https://dev.to/copyleftdev/cryptocurrency-rug-pull-scams-a-comprehensive-analysis-18ga
CONCENTRATED_MINT_PATTERNS = [
    # _mint(msg.sender, totalSupply) / _mint(owner, totalSupply) / _mint(_owner, totalSupply)
    re.compile(r'_mint\s*\(\s*(?:msg\.sender|owner|_owner)\s*,\s*(?:_totalSupply|totalSupply|TOTAL_SUPPLY)', re.IGNORECASE),
    # Matches direct balance assignment: _balances[msg.sender] = totalSupply
    re.compile(r'_balances\s*\[\s*(?:msg\.sender|owner|_owner)\s*]\s*=\s*(?:_totalSupply|totalSupply|TOTAL_SUPPLY)', re.IGNORECASE),
    # Older balanceOf instead of _balances
    re.compile(r'balanceOf\s*\[\s*(?:msg\.sender|owner|_owner)\s*]\s*=\s*(?:_totalSupply|totalSupply|TOTAL_SUPPLY)', re.IGNORECASE),
    # _mint(owner(), ...), any second argument
    re.compile(r'_mint\s*\(\s*owner\s*\(\s*\)\s*,', re.IGNORECASE),
    # _mint(treasury, ...) / _mint(marketingWallet, ...) / _mint(devWallet, ...) / _mint(wallet, ...)
    re.compile(r'_mint\s*\(\s*(?:treasury|marketingWallet|devWallet|wallet)\s*,', re.IGNORECASE),
    # _mint(msg.sender, initialSupply)
    re.compile(r'_mint\s*\(\s*msg\.sender\s*,\s*initialSupply', re.IGNORECASE),
    # Matches direct balance assignment to _msgSender(): _balances[_msgSender()] = ...
    re.compile(r'_balances\s*\[\s*_msgSender\s*\(\s*\)\s*]\s*=', re.IGNORECASE),
    # direct balance assignment to owner(): _balances[owner()] =
    re.compile(r'_balances\s*\[\s*owner\s*\(\s*\)\s*]\s*=', re.IGNORECASE)
]

# Sometimes LP drain occurs via a swap rather than removal of liquidity
# The contract sells a large token balance for ETH/BNB to wallet controlled by owner, silently draining value from the pool
# Reference: https://www.certik.com/blog/the-vanishing-act-how-exit-scammers-mint-new-tokens-undetected
# All chins presented in dataset use the same interface and function name
# Reference: https://forum.openzeppelin.com/t/purpose-of-uniswap-pancake-factory-and-router-and-integration-in-openzeppelin/13369/5
# Reference: https://developer.pancakeswap.finance/contracts/v2/router-v2
CONTRACT_SWAP_PATTERNS = [
    # swapExactTokensForETH / swapExactTokensForETHSupportingFeeOnTransferTokens router function
    re.compile(r'swapExactTokensForETH\w*\s*\(', re.IGNORECASE),
    # alternate variant of swapTokensForEth (relevant for some non-standard contracts)
    re.compile(r'swapTokensForEth\s*\(', re.IGNORECASE)
]

# Regex to check whether a swap call is restricted to owner, admin or operator
# Reference: https://docs.openzeppelin.com/contracts/5.x/access-control, https://docs.openzeppelin.com/contracts/5.x/api/access
OWNER_GUARD_PATTERNS = [
    # modifiers onlyOwner, onlyAdmin, or onlyOperator
    re.compile(r'only(?:Owner|Admin|Operator)', re.IGNORECASE),
    # require(msg.sender == owner) or require(msg.sender == _owner)
    re.compile(r'require\s*\(\s*msg\.sender\s*==\s*(?:owner|_owner)\b', re.IGNORECASE),
    # hasRole(...) call, OpenZeppelin
    re.compile(r'hasRole\s*\(', re.IGNORECASE),
    # onlyRole(...), OpenZeppelin
    re.compile(r'onlyRole\s*\(', re.IGNORECASE),
    # _checkOwner(), the internal OpenZeppelin's function
    re.compile(r'_checkOwner\s*\(', re.IGNORECASE),
    # DEFAULT_ADMIN_ROLE (the built-in role constant, OpenZeppelin)
    re.compile(r'DEFAULT_ADMIN_ROLE', re.IGNORECASE)
]

# Unlocked liquidity may be one of signs of rug-pull, since there are no mechanisms preventing developer from withdrawal
# Search for references to locking mechanisms, including names of widely-used third-party services and generic 'locker'
# to catch any less famous or wide-spread locking services
# Absence of lock in contract does not mean liquidity is unlocked, external services may be used, but still worth checking
# References: https://simplebaseswap.com/blog/rug-pulls-explained-how-liquidity-scams-work/, https://coingape.com/best-liquidity-lockers/
LP_LOCK_REFERENCE_PATTERNS = [
    # lockLiquidity (could be function or variable)
    re.compile(r'\blockLiquidity\b', re.IGNORECASE),
    # lockLP
    re.compile(r'\blockLP\b', re.IGNORECASE),
    # general pattern for 'locker'
    re.compile(r'locker\b', re.IGNORECASE),
    # PinkLock, third-party liquidity locking service
    re.compile(r'\bPinkLock\b', re.IGNORECASE),
    # TeamFinance, third-party liquidity locking service
    re.compile(r'\bTeamFinance\b', re.IGNORECASE),
    # UNCX, third-party liquidity locking service
    re.compile(r'\bUNCX\b', re.IGNORECASE),
    # unlockTime, the standard identifier for a stored unlock timestamp
    re.compile(r'\bunlockTime\b', re.IGNORECASE),
    # DxLock, third-party liquidity locking service
    re.compile(r'\bDxLock\b', re.IGNORECASE),
    # LiquidityLocker, third-party liquidity locking service
    re.compile(r'\bLiquidityLocker\b', re.IGNORECASE),
]

# Patterns for bytecode in .txt files (meaning that contract is not verified)
EVM_BYTECODE_PATTERN = re.compile(r'\b(?:PUSH\d*|JUMPDEST|MSTORE|SLOAD|SSTORE|REVERT)\b', re.IGNORECASE)

# Names for columns for enrichment
# 'Is_contract_verified' is added here for code simplicity, although it is not a sign of LP-drain,
# but could be a sign of scam in general. Extracted here, since the script checks .txt files to be bytecode
LP_DRAIN_FEATURE_NAMES = [
    'has_concentrated_initial_mint',
    'has_contract_swap_patterns',
    'has_owner_guard',
    'has_lp_lock_reference',
]

ALL_FEATURE_NAMES = LP_DRAIN_FEATURE_NAMES + ['is_contract_verified']

INPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_LP_drain_code_detection.xlsx' was used in original experiment
OUTPUT_FILE = "../data/placeholder.xlsx"


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


# Check whether source code is bytecode, not a Solidity file
# If .txt file does not contain Solidity code, it is technically unfeasible in this script to extract necessary features,
# so their values will be treated as missing in enriched dataset
def is_bytecode(source_code):
    opcode_hits = len(EVM_BYTECODE_PATTERN.findall(source_code))
    return opcode_hits > 20                 # 20 is chosen to prevent accidental matches, it is unlikely to hit 20+ times


# Detects common implementations of allocation full initial supply to a single address
# A precondition for control over liquidity, not a conclusive signal
def has_concentrated_initial_mint(source_code):
    return any(pattern.search(source_code) for pattern in CONCENTRATED_MINT_PATTERNS)


# Detects common implementations of a function that can swap its own token balance for base cryptocurrency (ETH/BNB/ARBI/POLYGON)
# A precondition for removal (swapping) liquidity, not a conclusive signal
def has_contract_swap_patterns(source_code):
    return any(pattern.search(source_code) for pattern in CONTRACT_SWAP_PATTERNS)


# Detects common implementations of a swap call is restricted to privileged accounts
# Could be a signal only in combination with has_contract_swap_patterns
def has_owner_guard(source_code):
    return any(pattern.search(source_code) for pattern in OWNER_GUARD_PATTERNS)


# Detects common implementations of any reference to a lock mechanism or known locker service
# Is not conclusive, since locking mechanisms can be implemented externally, without any source-code reference
def has_lp_lock_reference(source_code):
    return any(pattern.search(source_code) for pattern in LP_LOCK_REFERENCE_PATTERNS)


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