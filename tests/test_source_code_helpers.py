# Testing source_code_helplers

import math

import pytest

import feature_extraction_helpers.source_code_helplers as source_code


# Tests detection of contract swap patterns in input
@pytest.mark.parametrize("code, expected", [
    ('function swapTokensForEth(uint256 amount) private {', True),                       # common private swap helper
    ('router.swapExactTokensForETHSupportingFeeOnTransferTokens(amount);', True),        # long version
    ('function transfer(address to, uint256 value) public returns (bool) {', False),     # ordinary ERC-20 code
    ('', False),                                                                         # empty source
])
def test_has_contract_swap_patterns(code, expected):
    assert source_code.has_contract_swap_patterns(code) is expected


# Tests detection of owner or role guards restricting calls to privileged accounts
@pytest.mark.parametrize("code, expected", [
    ('function withdraw() external onlyOwner {', True),                    # OpenZeppelin modifier
    ('require(msg.sender == _owner, "not owner");', True),                 # manual owner check
    ('if (hasRole(MANAGER_ROLE, msg.sender)) {', True),                    # role-based access control
    ('function transfer(address to, uint256 value) public {', False),      # no guard
])
def test_has_owner_guard(code, expected):
    assert source_code.has_owner_guard(code) is expected


# Tests detection of concentrated initial mint patterns (entire supply to a single address)
@pytest.mark.parametrize("code, expected", [
    ('_mint(msg.sender, totalSupply);', True),                # entire supply minted to deployer
    ('_balances[owner()] = _totalSupply;', True),             # direct balance assignment to owner
    ('_mint(recipient, amount);', False),                     # an ordinary parameterised mint
])
def test_has_concentrated_initial_mint(code, expected):
    assert source_code.has_concentrated_initial_mint(code) is expected


# Tests detection of liquidity lock references
@pytest.mark.parametrize("code, expected", [
    ('// liquidity locked via PinkLock', True),           # a known locking service
    ('IPinkLock(pinkLockAddress).lock(1);', True),        # a known locking service as a part of another word
    ('uint256 public unlockTime;', True),                 # a standard unlock timestamp identifier
    ('function transfer() public {', False),              # no lock references
])
def test_has_lp_lock_reference(code, expected):
    assert source_code.has_lp_lock_reference(code) is expected


# Tests bytecode detector threshold (>20 opcode hits), including edge case
@pytest.mark.parametrize("opcode_hits, expected", [
    (25, True),         # clearly bytecode
    (21, True),         # just over the threshold
    (20, False),        # exactly at the threshold, still treated as valid
    (0, False),         # ordinary Solidity text
])
def test_is_bytecode_threshold(opcode_hits, expected):
    assert source_code.is_bytecode('PUSH1 ' * opcode_hits + 'contract Token {}') is expected


# Tests source normalisation
def test_normalise_source_code():
    # plain text
    plain = 'contract Token { }'
    assert source_code.normalise_source_code(plain) == plain
    # valid multi-file response
    multi_file = '{' + '{"sources": {"A.sol": {"content": "contract A {}"}, "B.sol": {"content": "contract B {}"}}}' + '}'
    assert source_code.normalise_source_code(multi_file) == 'contract A {}\ncontract B {}'
    # malformed JSON
    malformed = '{{not valid json}}'
    assert source_code.normalise_source_code(malformed) == malformed


# Tests live code-feature extraction
@pytest.mark.parametrize("etherscan_data, expected_swap, expected_guard", [
    # verified contract containing a guarded swap -> both flags set
    ({'result': [{'SourceCode': 'function f() onlyOwner { swapTokensForEth(1); }'}]}, 1, 1),
    # verified contract with neither pattern -> both flags zero
    ({'result': [{'SourceCode': 'contract Plain { }'}]}, 0, 0),
    # unverified contract (empty SourceCode) -> both features are missing values
    ({'result': [{'SourceCode': ''}]}, math.nan, math.nan),
    # Etherscan call failed -> both features are missing values
    (None, math.nan, math.nan),
])
def test_get_source_code_features_live(monkeypatch, etherscan_data, expected_swap, expected_guard):
    monkeypatch.setattr(source_code, 'query_etherscan', lambda chain, params: etherscan_data)
    result = source_code.get_source_code_features_live('ETH', '0xabc')
    for key, expected in (('has_contract_swap_patterns', expected_swap), ('has_owner_guard', expected_guard)):
        assert result[key] == expected or (isinstance(expected, float) and math.isnan(expected) and math.isnan(result[key]))