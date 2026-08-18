# Extracts 'MaxPrice (Quarter 1)' and 'MaxPrice (Quarter 2)' features for a live-queried token (consumed by the model).
# Finds maximum price for the first two windows within 4 periods, calculated as a time window between the project deployment /
# first pool creation and project end (for scam) or query date (for live tokens) divided by 4.
# Preserves temporal hygiene according to TM-RugPull methodology, no data from the token's later life is ever requested and used.
#
# Uses two data sources:
# (1) CoinGecko API, coin market_chart/range endpoint: a primary call attempted, since it returns necessary data in one call for free,
#     but it requires a token to be already listed and tracked, which could not be a case for rug-pull tokens which may
#     live only one or several days;
#     Reference: https://docs.coingecko.com/reference/contract-address-market-chart-range
# (2) GeckoTerminal API: works for any token, if on-chain liquidity pool was created, gets data directly from swap activity, but
#     requires several API calls and pagination: it needs to find relevant pool / pools, then returns OHLCV for a specific pool.
#     Reference: https://docs.coingecko.com/docs/keyless-public-api
# TODO: amend considering depth historical limits, try Moralis?
# TODO: try this route: young tokens → try GeckoTerminal (more DEXes / coins), old tokens → try Moralis first (no documented historical depth cap)

import math
import time
from datetime import datetime, timezone

from feature_extraction_helpers.config import COINGECKO_CHAIN_IDS, GECKOTERMINAL_NETWORK_IDS, MORALIS_CHAIN_IDS
from feature_extraction_helpers.general_onchain_helpers import query_coingecko, get_last_activity_timestamp, \
    is_token_live, get_deployment_block_and_timestamp, get_latest_block_with_timestamp, query_geckoterminal, \
    query_moralis

# Thresholds to pick OHLCV candle resolution based on window length, based on CoinGecko convention.
# More granularity for short living tokens (to catch rug-pull), increasing for long-living projects due to
# efficiency reasons and API limits
# Reference: https://docs.coingecko.com/reference/pool-ohlcv-contract-address
GECKO_OHLCV_THRESHOLDS_SECONDS = (
    (2 * 24 * 3600, 'minute', 15),   # for window <= 2 days: 15-minute candles
    (60 * 24 * 3600, 'hour', 1),     # for window <= 60 days: 1-hour candles
    (float('inf'), 'day', 1),        # for anything longer: daily candles
)

# Moralis timeframe enum values (1s, 10s, 30s, 1min, 5min, 10min, 30min, 1h, 4h, 12h, 1d, 1w, 1M)
# Reference: https://docs.moralis.com/data-api/evm/price/ohlc
MORALIS_TIMEFRAME_THRESHOLDS_SECONDS = (
    (2 * 24 * 3600, '10min'),   # window <= 2 days: 10-minute candles
    (60 * 24 * 3600, '1h'),    # window <= 60 days: 1-hour candles
    (float('inf'), '1d'),      # anything longer: daily candles
)


# Primary path, works only for tokens CoinGecko already tracks
# Caches every 5 minutes for Demo plan
# Reference: https://docs.coingecko.com/demo/reference/contract-address-market-chart-range
def get_prices_coingecko(blockchain, token_address, from_timestamp, to_timestamp):
    blockchain = COINGECKO_CHAIN_IDS.get(blockchain)
    if blockchain is None:
        return None
    data = query_coingecko(
f"/coins/{blockchain}/contract/{token_address}/market_chart/range",
        params={'vs_currency': 'usd', 'from': from_timestamp, 'to': to_timestamp},
    )
    if data is None or not data.get('prices'):
        return None

    print(f"CoinGecko path succeeded for {token_address} on {blockchain}")
    # CoinGecko timestamps are in milliseconds, normalizing required to match CoinGeckoTerminal
    return [(timestamp_ms / 1000, price) for timestamp_ms, price in data['prices']]


# CoinGecko Terminal contains on-chain information about pools created involving a particular address, thus,
# to query prices it is necessary to find related pools. Chooses a pull with most money (most representative for
# prices extraction) + the earliest pool to get starting point for prices extraction (before the first pool, there are
# no prices)
# Cached every 60 seconds for Demo plan
# Reference: https://docs.coingecko.com/demo/reference/top-pools-contract-address
def get_top_pool_address(chain, token_address):
    network = GECKOTERMINAL_NETWORK_IDS[chain]
    data = query_geckoterminal(f"/networks/{network}/tokens/{token_address}/pools")
    if data is None or not data.get('data'):
        print(f"No pools found for {token_address} on {chain}")
        return None, None, None

    candidate_pools = []
    for pool in data['data']:
        base_token_id = pool.get('relationships', {}).get('base_token', {}).get('data', {}).get('id', '')
        quote_token_id = pool.get('relationships', {}).get('quote_token', {}).get('data', {}).get('id', '')
        if token_address.lower() not in base_token_id.lower() and token_address.lower() not in quote_token_id.lower():
            continue
        reserve_in_usd = float(pool.get('attributes', {}).get('reserve_in_usd') or 0)
        pool_created_at = pool.get('attributes', {}).get('pool_created_at')
        candidate_pools.append((reserve_in_usd, pool['attributes']['address'], pool_created_at))

    if not candidate_pools:
        return None, None, None

    candidate_pools.sort(key=lambda item: item[0], reverse=True)
    top_pool = candidate_pools[0]
    top_reserve, top_pool_address, top_pool_created_at = top_pool[0], top_pool[1], top_pool[2]
    pools_with_creation_date = [pool for pool in candidate_pools if pool[2] is not None]
    earliest_reserve, earliest_pool_address, earliest_pool_created_at = min(pools_with_creation_date, key=lambda item: item[2])
    print(f"Selected pool {top_pool_address} with reserve ${top_reserve:,.0f}; earliest pool {earliest_pool_address} created {earliest_pool_created_at}")

    return top_pool_address, earliest_pool_created_at, earliest_pool_address


# Convert GeckoTerminal's ISO 8601 timestamp into a unix timestamp
def parse_pool_created_at(pool_created_at):
    return int(datetime.strptime(pool_created_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())


# Determine a time window depending on inspected period for CoinGecko
def choose_ohlcv_timeframe_gecko(window_seconds):
    for max_seconds, timeframe, aggregate in GECKO_OHLCV_THRESHOLDS_SECONDS:
        if window_seconds <= max_seconds:
            return timeframe, aggregate


# Determine a time window depending on inspected period for Moralis
def choose_moralis_timeframe(window_seconds):
    for max_seconds, timeframe in MORALIS_TIMEFRAME_THRESHOLDS_SECONDS:
        if window_seconds <= max_seconds:
            return timeframe


# Get aggregated prices from a chosen pool
# Cached every 60 seconds for Demo plan
# Reference: https://docs.coingecko.com/demo/reference/pool-ohlcv-contract-address
def get_ohlcv_history(chain, pool_address, from_timestamp, to_timestamp):
    network = GECKOTERMINAL_NETWORK_IDS[chain]
    timeframe, aggregate = choose_ohlcv_timeframe_gecko(to_timestamp - from_timestamp)
    print(f"Fetching {timeframe} candles (aggregate={aggregate}) for pool {pool_address} via GeckoTerminal")

    all_candles = []
    cursor_timestamp = to_timestamp
    while cursor_timestamp > from_timestamp:
        data = query_geckoterminal(
            f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}",
            params={'aggregate': aggregate, 'before_timestamp': cursor_timestamp, 'limit': 1000, 'currency': 'usd'},
        )
        if data is None:
            return all_candles, True

        candles = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
        if not candles:
            break
        all_candles.extend(candles)

        oldest_timestamp = min(candle[0] for candle in candles)
        if oldest_timestamp >= cursor_timestamp:
            break
        cursor_timestamp = oldest_timestamp

    return all_candles, False


# Flatten OHLCV candles [timestamp, open, high, low, close, volume] into (timestamp, price) pairs, uses 'high' price for each candle
def transform_candles_to_prices(candles):
    return [(candle[0], candle[2]) for candle in candles]


# Attempts the GeckoTerminal path end-to-end
def try_geckoterminal_source(chain, token_address, window_end):
    top_pool_address, earliest_pool_created_at, earliest_pool_address = get_top_pool_address(chain, token_address)
    if top_pool_address is None:
        return None, None
    window_start = parse_pool_created_at(earliest_pool_created_at)
    candles, had_failure = get_ohlcv_history(chain, top_pool_address, window_start, window_end)
    if had_failure or not candles:
        return None, None

    prices = transform_candles_to_prices(candles)
    # Checks whether full history up to window_start + 5 minutes (fixed source boundary for collection prices) is returned
    # If not, fetch the highest prices available from either top pool, or the earliest pool
    if candles[-1][0] > window_start + 300 and earliest_pool_address != top_pool_address:
        print(f"Pool {top_pool_address} doesn't reach window start, retrying with earliest pool {earliest_pool_address}")
        earliest_candles, earliest_had_failure = get_ohlcv_history(chain, earliest_pool_address, window_start, window_end)
        if not earliest_had_failure and earliest_candles:
            prices += transform_candles_to_prices(earliest_candles)

    return window_start, prices


# Extract the maximum price for a specified range
def get_max_price_in_range(prices, from_timestamp, to_timestamp):
    prices_in_range = [price for timestamp, price in prices if from_timestamp <= timestamp < to_timestamp]
    if not prices_in_range:
        return math.nan
    return max(prices_in_range)


# Determine the end of the quarter window: query time for active tokens and last activity timestamp for dead tokens
def get_window_end_timestamp(chain, token_address, latest_block_timestamp):
    last_activity_timestamp = get_last_activity_timestamp(chain, token_address)
    if is_token_live(last_activity_timestamp, latest_block_timestamp):
        return int(time.time())
    if last_activity_timestamp is not None:
        return last_activity_timestamp
    # No activity ever recorded, use time of query
    return int(time.time())


# Calculate quarters to use for price extraction
def compute_quarters(prices, window_start, window_end, price_source):
    quarter_length_seconds = (window_end - window_start) / 4
    if quarter_length_seconds <= 0:
        return {'MaxPrice (Quarter 1)': math.nan, 'MaxPrice (Quarter 2)': math.nan, 'price_source': price_source}

    q1_start = window_start
    q1_end = window_start + quarter_length_seconds
    q2_end = window_start + 2 * quarter_length_seconds

    return {
        'MaxPrice (Quarter 1)': get_max_price_in_range(prices, q1_start, q1_end),
        'MaxPrice (Quarter 2)': get_max_price_in_range(prices, q1_end, q2_end),
        'price_source': price_source,
    }


# Extract pools information for a specified token address via Moralis, return top pool for further query for prices
# https://docs.moralis.com/data-api/evm/token/swaps/token-pairs
def get_top_pool_moralis(chain, token_address):
    moralis_chain = MORALIS_CHAIN_IDS.get(chain)
    if moralis_chain is None:
        return None

    data = query_moralis(f"/erc20/{token_address}/pairs", params={'chain': moralis_chain})
    if data is None or not data.get('pairs'):
        print(f"No trading pairs found for {token_address} on {chain}")
        return None

    candidate_pairs = []
    for pair in data['pairs']:
        base_token = pair.get('base_token', '')
        quote_token = pair.get('quote_token', '')
        if token_address.lower() not in (base_token.lower(), quote_token.lower()):
            continue
        pair_address = pair.get('pair_address')
        if pair_address is None:
            continue
        liquidity_usd = float(pair.get('liquidity_usd') or 0)
        candidate_pairs.append((liquidity_usd, pair_address))

    if not candidate_pairs:
        return None

    candidate_pairs.sort(key=lambda item: item[0], reverse=True)
    top_pair = candidate_pairs[0]
    top_liquidity, top_pair_address  = top_pair[0], top_pair[1]
    print(f"Selected pair {top_pair_address} with liquidity ${top_liquidity:,.0f}")

    return top_pair_address


# Get the earliest swap for a token (order=ASC, limit=1) to get timestamp of trade start
# Reference: https://docs.moralis.com/data-api/evm/token/swaps/token-swaps
def get_first_swap_timestamp_moralis(chain, token_address):
    moralis_chain = MORALIS_CHAIN_IDS.get(chain)
    if moralis_chain is None:
        return None

    data = query_moralis(f"/erc20/{token_address}/swaps", params={'chain': moralis_chain, 'order': 'ASC', 'limit': 1})
    if data is None or not data.get('result'):
        print(f"No swaps found for {token_address} on {chain}")
        return None

    first_swap = data['result'][0]
    block_timestamp = first_swap.get('blockTimestamp')
    if block_timestamp is None:
        return None

    return parse_moralis_timestamp(block_timestamp)


# Convert Moralis's ISO 8601 timestamp into a unix timestamp
def parse_moralis_timestamp(timestamp_str):
    return int(datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).timestamp())


# Get aggregated prices for a Moralis pair
# Reference: https://docs.moralis.com/data-api/evm/token/prices/ohlc
def get_prices_moralis_pair(chain, pair_address, from_timestamp, to_timestamp):
    moralis_chain = MORALIS_CHAIN_IDS.get(chain)
    timeframe = choose_moralis_timeframe(to_timestamp - from_timestamp)
    print(f"Fetching {timeframe} candles for pair {pair_address} via Moralis")

    all_prices = []
    cursor = None
    while True:
        params = {'chain': moralis_chain, 'timeframe': timeframe, 'currency': 'usd',
                   'fromDate': from_timestamp, 'toDate': to_timestamp, 'limit': 1000}
        if cursor:
            params['cursor'] = cursor
        data = query_moralis(f"/pairs/{pair_address}/ohlcv", params=params)
        if data is None:
            return all_prices, True

        candles = data.get('result', [])
        for candle in candles:
            all_prices.append((parse_moralis_timestamp(candle['timestamp']), candle['high']))

        cursor = data.get('cursor')
        if not cursor or not candles:
            break

    return all_prices, False


# Attempts Moralis path end-to-end
def try_moralis_source(chain, token_address, deployment_timestamp, window_end):
    pair_address = get_top_pool_moralis(chain, token_address)
    if pair_address is None:
        return None, None
    # Moralis API does not provide info about the earliest pool and timestamps for pools, thus, window_start is determined
    # by the first swap event (meaning, that the token began trading activity). If no swaps, deployment timestamp is used
    first_swap_timestamp = get_first_swap_timestamp_moralis(chain, token_address)
    window_start = first_swap_timestamp if first_swap_timestamp is not None else deployment_timestamp

    prices, had_failure = get_prices_moralis_pair(chain, pair_address, window_start, window_end)
    if had_failure or not prices:
        return None, None

    return window_start, prices


# Extract 'MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)' for a live-queried token
# Tries CoinGecko API first. If a queried token is not listed here (code 404), tries GeckoTerminal with pool-resolution
def get_max_price_quarters_live(chain, token_address, deployment_timestamp, latest_block_timestamp):
    print("MaxPrice (Quarter 1)/(Quarter 2) are calculating...")
    window_end = get_window_end_timestamp(chain, token_address, latest_block_timestamp)

    prices = get_prices_coingecko(chain, token_address, deployment_timestamp, window_end)
    if prices is not None:
        result = compute_quarters(prices, deployment_timestamp, window_end, 'coingecko')
        if not (math.isnan(result['MaxPrice (Quarter 1)']) and math.isnan(result['MaxPrice (Quarter 2)'])):
            return result
        print(f"CoinGecko data for {token_address} on {chain} doesn't cover Q1/Q2, trying GeckoTerminal")
    else:
        print(f"CoinGecko has no data for {token_address} on {chain}, trying GeckoTerminal")

    window_start, prices = try_geckoterminal_source(chain, token_address, window_end)
    if prices is None:
        return {'MaxPrice (Quarter 1)': math.nan, 'MaxPrice (Quarter 2)': math.nan, 'price_source': None}

    return compute_quarters(prices, window_start, window_end, 'geckoterminal')


def main():
    address = '0xB91025710Adbc140a9fEe4b3E465545a2bF53E20'
    chain = 'POLYGON'
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, address)
    latest_block, latest_block_timestamp = get_latest_block_with_timestamp(chain)
    # prices = get_max_price_quarters_live(chain, address, deployment_timestamp, latest_block_timestamp)
    # print(prices)
    window_end = get_window_end_timestamp(chain, address, latest_block_timestamp)
    window_start, prices = try_moralis_source(chain, address, deployment_timestamp, window_end)
    print(window_start, prices)





if __name__ == "__main__":
    main()



# For testing:
# Geckoterminal, success
#     address = '0x100acD9FcD8E0FF80A6595B66fdABe93184Aa100'
#     chain = 'ETH'
#     address = '0xB91025710Adbc140a9fEe4b3E465545a2bF53E20'
#     chain = 'POLYGON'
# CoinGecko has token listed, but does not have price history for required periods (nans for Q1/Q2), fall back to terminal, success
#     address = '0x3cdb41027d61c413e064e84d9c21812b6ef004f1'
#     chain = 'ETH'
# Top pool does not reach window start, use the earliest pool (GeckoTerminal)
#     address = '0x951f086a127e280724fd93ccc543f65065afeb5e'
#     chain = 'ETH'

# 401 for CoinGecko (too deep), try with Moralis later
    # address = '0x0c29891dc5060618c779e2a45fbe4808aa5ae6ad'
    # chain = 'ARBI'