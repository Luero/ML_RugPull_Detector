# TODO: general comment

import json
import math

from feature_extraction_helpers.general_extraction_helpers import query_etherscan
from feature_extraction_helpers.source_code_helplers import is_bytecode, has_contract_swap_patterns, has_owner_guard


# Extract source code for a token contract via Etherscan
# Works uniformly for all supported chains on free plan: https://docs.etherscan.io/supported-chains
# Reference: https://docs.etherscan.io/api-reference/endpoint/getsourcecode
def get_contract_source_code(chain, token_address):
    data = query_etherscan(chain, {'module': 'contract', 'action': 'getsourcecode', 'address': token_address})
    if data is None or not data.get('result'):
        print(f"Could not get source code for {token_address} on {chain}")
        return None
    result = data['result'][0]
    source_code = result.get('SourceCode')
    if not source_code:
        print(f"Contract {token_address} on {chain} is not verified")
        return None

    normalized_source_code = normalize_source_code(source_code)
    print(normalized_source_code)

    return normalized_source_code


# Flat source code from row response into a single string to apply regex patterns, if multiple files
# If there is one file, return as plain Solidity source
def normalize_source_code(source_code):
    # Multy-file responses are wrapped in {{ }}
    if not (source_code.startswith('{{') and source_code.endswith('}}')):
        return source_code
    try:
        parsed = json.loads(source_code[1:-1])
    except json.JSONDecodeError as e:
        print(f"Could not parse source code: {e}")
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


def main():
    print(get_source_code_features_live('ETH', '0x582d872A1B094FC48F5DE31D3B73F2D9bE47def1'))


if __name__ == "__main__":
    main()