# TODO: general comment

import json

from feature_extraction_helpers.general_onchain_helpers import query_etherscan


# Etherscan wraps multi-file submissions in extra pair of curly braces
# Reference: https://docs.etherscan.io/api-reference/endpoint/getsourcecode
MULTI_FILE_WRAPPER_PREFIX = '{{'
MULTI_FILE_WRAPPER_SUFFIX = '}}'


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

    return normalize_source_code(source_code)


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




def main():
    print(get_contract_source_code('BSC', '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00'))


if __name__ == "__main__":
    main()