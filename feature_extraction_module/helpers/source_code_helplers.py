# Contains constants and functions to retrieve code-based features. Used both for the dataset enrichment and for
# live feature extraction pipeline.
#
# Code-based features are extracted based on regex patterns relevant for Solidity contract code, including OpenZeppelin library.
# Source code for the dataset enrichment is retrieved from .txt files saved locally. Source code for a live pipeline is
# obtained via Etherscan.


import re
import json
import math

from feature_extraction_module.helpers.general_extraction_helpers import query_etherscan

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
    re.compile(r'PinkLock\b', re.IGNORECASE),
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


# Extract source code for a token contract via Etherscan
# Works uniformly for all supported chains on free plan: https://docs.etherscan.io/supported-chains
# Reference: https://docs.etherscan.io/api-reference/endpoint/getsourcecode
def get_contract_source_code(chain, token_address):
    data = query_etherscan(chain, {'module': 'contract', 'action': 'getsourcecode', 'address': token_address})
    if data is None or not data.get('result'):
        print(f"...Could not get source code for {token_address} on {chain}")
        return None
    result = data['result'][0]
    source_code = result.get('SourceCode')
    if not source_code:
        print(f"...Contract {token_address} on {chain} is not verified")
        return None
    normalised_source_code = normalise_source_code(source_code)
    return normalised_source_code


# Flat source code from row response into a single string to apply regex patterns, if multiple files
# If there is one file, return as plain Solidity source
def normalise_source_code(source_code):
    # Multy-file responses are wrapped in {{ }}
    if not (source_code.startswith('{{') and source_code.endswith('}}')):
        return source_code
    try:
        parsed = json.loads(source_code[1:-1])
    except json.JSONDecodeError as e:
        print(f"...Could not parse source code: {e}")
        return source_code
    sources = parsed.get('sources', {})
    return '\n'.join(file_data.get('content', '') for file_data in sources.values())


# Extract 'has_contract_swap_patterns', 'has_owner_guard' features for a live-queried token
# Missing values or unverified contracts (bytecode only) are treated as missing values for prediction module
def get_source_code_features_live(chain, token_address):
    print("Code-based features are calculating...")
    source_code = get_contract_source_code(chain, token_address)
    if source_code is None:
        return {'has_contract_swap_patterns': math.nan, 'has_owner_guard': math.nan}
    return {
        'has_contract_swap_patterns': int(has_contract_swap_patterns(source_code)),
        'has_owner_guard': int(has_owner_guard(source_code)),
    }