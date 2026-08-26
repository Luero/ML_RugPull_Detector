# Testing holders_count_helpers, including transfer-replay holder counting logic and snapshot block resolution
# Does not require real connection

import math

import pytest

import feature_extraction_helpers.holders_count_helpers as holders
from feature_extraction_helpers.config import TRANSFER_EVENT_HASH

ZERO_ADDRESS = '0x' + '0' * 40
ADDRESS_A = '0x' + 'a' * 40
ADDRESS_B = '0x' + 'b' * 40


# Builds a transfer event log like Etherscan returns
def make_log(block_number, from_address, to_address, value):
    return {
        'address': '0x' + 'c' * 40,
        'blockNumber': hex(block_number),
        'topics': [TRANSFER_EVENT_HASH, '0x' + 24 * '0' + from_address[2:], '0x' + 24 * '0' + to_address[2:]],
        'data': hex(value),
    }


# Mint 100 to A at block 1, A sends 40 to B at block 3, B sends all 40 back at block 5
REPLAY_LOGS = [
    make_log(1, ZERO_ADDRESS, ADDRESS_A, 100),
    make_log(3, ADDRESS_A, ADDRESS_B, 40),
    make_log(5, ADDRESS_B, ADDRESS_A, 40),
]


# Tests the transfer replay. Holders are addresses with positive balances at each target block,
@pytest.mark.parametrize("target_blocks, expected", [
    # snapshot right after the mint: A is the single holder
    ({12: 2}, {'Holders_12h': 1}),
    # two snapshots: after the mint (1 holder) and after the split transfer (2 holders)
    ({12: 2, 24: 4}, {'Holders_12h': 1, 'Holders_24h': 2}),
    # snapshot beyond the last log: B's balance is emptied back to zero, so only A counts
    ({12: 6}, {'Holders_12h': 1}),
])
def test_count_holders_for_snapshots_replay(target_blocks, expected):
    assert holders.count_holders_for_snapshots(REPLAY_LOGS, target_blocks) == expected


# Tests that a zero-value mint does not create a holder
def test_count_holders_for_snapshots_ignores_zero_balances():
    logs = [make_log(1, ZERO_ADDRESS, ADDRESS_A, 0)]
    assert holders.count_holders_for_snapshots(logs, {12: 2}) == {'Holders_12h': 0}


# Tests that an unsupported transfer event format returns None for the whole replay
def test_count_holders_for_snapshots_unsupported_event():
    unsupported = dict(make_log(1, ZERO_ADDRESS, ADDRESS_A, 100), data='0x')
    assert holders.count_holders_for_snapshots([unsupported], {12: 2}) is None


# Tests transfer value extraction across ERC-20 event formats, including 0 value edge case
@pytest.mark.parametrize("log_overrides, expected_value", [
    # standard ERC-20 event (the value is in the data field)
    ({'data': hex(100)}, 100),
    # standard event with 0 value (parsed as 0, not treated as missing)
    ({'data': '0x' + '0' * 64}, 0),
    # non-standard event with an indexed value (taken from the last of four topics)
    ({'data': '0x', 'topics': [TRANSFER_EVENT_HASH, 'f', 't', hex(55)]}, 55),
    # no value anywhere (None, the token will be treated as unsupported)
    ({'data': '0x'}, None),
])
def test_get_transfer_value_from_log(log_overrides, expected_value):
    log = dict(make_log(1, ZERO_ADDRESS, ADDRESS_A, 1), **log_overrides)
    assert holders.get_transfer_value_from_log(log) == expected_value


# Tests block number extraction from a log for different formats
@pytest.mark.parametrize("block_number_value, expected", [
    ('0x10', 16),           # hexadecimal string, as Etherscan returns it
    (16, 16),               # plain integer, as NodeReal returns it
])
def test_get_block_number_from_log(block_number_value, expected):
    assert holders.get_block_number_from_log({'blockNumber': block_number_value}) == expected


# Tests that a 32-byte padded topic is cut down to the 20-byte address
def test_get_address_from_topic():
    assert holders.get_address_from_topic('0x' + 24 * '0' + 'a' * 40) == ADDRESS_A


# Tests NodeReal log-limit handling
def test_get_transfer_logs_bsc_splits_on_limit(monkeypatch):
    # Mock Meganode behaviour on rate limit
    def fake_meganode(method, params):
        from_block, to_block = int(params[0]['fromBlock'], 16), int(params[0]['toBlock'], 16)
        if (from_block, to_block) == (0, 10):
            return 'LOG_LIMIT_EXCEEDED'
        return [make_log(from_block, ZERO_ADDRESS, ADDRESS_A, 1)]
    monkeypatch.setattr(holders, 'query_meganode', fake_meganode)
    logs, had_failure = holders.get_transfer_logs_bsc('0xTOKEN', 0, 10)
    # both halves fetched after the split
    assert len(logs) == 2 and had_failure is False

    monkeypatch.setattr(holders, 'query_meganode', lambda method, params: 'LOG_LIMIT_EXCEEDED')
    logs, had_failure = holders.get_transfer_logs_bsc('0xTOKEN', 7, 7)
    # a single block over the limit cannot be split
    assert logs == [] and had_failure is True


# Tests Etherscan's get_block_number_by_timestamp endpoint path to obtain holders snapshots
def test_get_holders_snapshots_fast_path(monkeypatch):
    fetched_ranges = []
    monkeypatch.setattr(holders, 'get_block_number_by_timestamp',
                        lambda chain, ts: 5000 if ts == 1700000000 + 12 * 3600 else 6000)
    monkeypatch.setattr(holders, 'get_transfer_logs',
                        lambda chain, addr, f, t: (fetched_ranges.append((f, t)), ([], False))[1])
    result = holders.get_holders_snapshots('ETH', '0xABC', (12, 24), deployment_block=100, deployment_timestamp=1700000000)
    assert result == {'Holders_12h': 0, 'Holders_24h': 0}
    assert fetched_ranges == [(100, 6000)]


# Tests binary search path, if API call cannot return a timestamp of relevant block
def test_get_holders_snapshots_binary_search_fallback(monkeypatch):
    binary_calls = []
    monkeypatch.setattr(holders, 'get_block_number_by_timestamp',
                        lambda chain, ts: None if ts == 1700000000 + 24 * 3600 else 5000)
    monkeypatch.setattr(holders, 'get_latest_block_eth', lambda chain: 999999)
    monkeypatch.setattr(holders, 'find_block_by_timestamp',
                        lambda chain, ts, low, high: (binary_calls.append((ts, low, high)), 5500)[1])
    monkeypatch.setattr(holders, 'get_transfer_logs', lambda chain, addr, f, t: ([], False))
    result = holders.get_holders_snapshots('ARBI', '0xBAL', (12, 24), deployment_block=100, deployment_timestamp=1700000000)
    assert result == {'Holders_12h': 0, 'Holders_24h': 0}
    assert binary_calls == [(1700000000 + 24 * 3600, 100, 999999)]


# Tests that when no snapshot block is found, every snapshot becomes a missing value
def test_get_holders_snapshots_total_resolution_failure(monkeypatch):
    monkeypatch.setattr(holders, 'get_block_number_by_timestamp', lambda chain, ts: None)
    monkeypatch.setattr(holders, 'get_latest_block_eth', lambda chain: None)
    result = holders.get_holders_snapshots('ARBI', '0xBAL', (12, 24), deployment_block=100, deployment_timestamp=1700000000)
    assert all(math.isnan(value) for value in result.values())


# Tests snapshot receiving for BSC via approximation of block time
def test_get_holders_snapshots_bsc_approximation(monkeypatch):
    endpoint_calls = []
    fetched_ranges = []
    monkeypatch.setattr(holders, 'get_block_number_by_timestamp',
                        lambda chain, ts: endpoint_calls.append(ts))
    monkeypatch.setattr(holders, 'get_transfer_logs',
                        lambda chain, addr, f, t: (fetched_ranges.append((f, t)), ([], False))[1])
    # November 2023, BSC block time is 3.01 sec
    deployment_timestamp = 1700000000
    result = holders.get_holders_snapshots('BSC', '0xABC', (12, 24), deployment_block=1000, deployment_timestamp=deployment_timestamp)
    assert result == {'Holders_12h': 0, 'Holders_24h': 0}
    assert endpoint_calls == []
    assert fetched_ranges == [(1000, 1000 + int(24 * 3600 / 3.01))]