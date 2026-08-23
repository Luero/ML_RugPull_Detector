# Extracts 'MaxPrice (Quarter 1)' and 'MaxPrice (Quarter 2)' features for a live-queried token (consumed by the model).
# Finds maximum price for the first two windows within 4 periods, calculated as a time window between the project deployment /
# first pool creation and project end (for scam) or query date (for live tokens) divided by 4.
# Preserves temporal hygiene according to TM-RugPull methodology, no data from the token's later life is ever requested and used.
#
# Uses three data sources:
# (1) CoinGecko API, /contract-address-market-chart-range endpoint: a primary call attempted, since it returns necessary data in one call for free,
#     but it requires a token to be already listed and tracked, which could not be a case for rug-pull tokens which may
#     live only one or several days;
#     Reference: https://docs.coingecko.com/demo/reference/contract-address-market-chart-range
# (2) GeckoTerminal API: works for any token, if on-chain liquidity pool was created, gets data directly from swap activity, but
#     requires several API calls and pagination: it needs to find relevant pool / pools, then returns OHLCV for a specific pool.
#     It has a historical depth limit of 180 days for retrieving prices, thus, it is used to get timestamp of the earliest pool created and,
#     if it is within depth limit, query for prices;
#     Reference: https://docs.coingecko.com/docs/keyless-public-api
# (3) Moralis API: used as a secondary source, if GeckoTerminal hits its historical depth limit of 180 days. Moralis has less coverage
#     (fewer chains and DEXes), but does not have a limit for historical requests, so it is useful when a long-living token is queried.


import math
import time
from datetime import datetime, timezone

from feature_extraction_helpers.config import COINGECKO_CHAIN_IDS, GECKOTERMINAL_NETWORK_IDS, MORALIS_CHAIN_IDS, \
    GECKOTERMINAL_MAX_DEPTH_SECONDS
from feature_extraction_helpers.general_extraction_helpers import query_coingecko, get_last_activity_timestamp, \
    is_token_live, get_deployment_block_and_timestamp, get_latest_block_with_timestamp, query_geckoterminal, \
    query_moralis

# Thresholds to pick OHLCV candle resolution based on window length, based on CoinGecko convention.
# More granularity for short living tokens (to catch rug-pull), increasing for long-living projects due to
# efficiency reasons and API limits
# Reference: https://docs.coingecko.com/reference/pool-ohlcv-contract-address
GECKO_OHLCV_THRESHOLDS_SECONDS = (
    (2 * 24 * 3600, 'second', 30),   # for window <= 2 days: 30-seconds candles
    (60 * 24 * 3600, 'hour', 1),     # for window <= 60 days: 1-hour candles
    (float('inf'), 'day', 1),        # for anything longer: daily candles
)

# Moralis timeframe enum values (1s, 10s, 30s, 1min, 5min, 10min, 30min, 1h, 4h, 12h, 1d, 1w, 1M)
# Reference: https://docs.moralis.com/data-api/evm/price/ohlc
MORALIS_TIMEFRAME_THRESHOLDS_SECONDS = (
    (2 * 24 * 3600, '30s'),    # window <= 2 days: 30-seconds candles
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
        return None, None, None, None, None

    candidate_pools = []
    for pool in data['data']:
        base_token_id = pool.get('relationships', {}).get('base_token', {}).get('data', {}).get('id', '')
        quote_token_id = pool.get('relationships', {}).get('quote_token', {}).get('data', {}).get('id', '')
        if token_address.lower() not in base_token_id.lower() and token_address.lower() not in quote_token_id.lower():
            continue
        reserve_in_usd = float(pool.get('attributes', {}).get('reserve_in_usd') or 0)
        pool_created_at = pool.get('attributes', {}).get('pool_created_at')
        # To ensure the price is in USD (as per docs for the base token)
        token_side = 'base' if token_address.lower() in base_token_id.lower() else 'quote'
        candidate_pools.append((reserve_in_usd, pool['attributes']['address'], pool_created_at, token_side))

    if not candidate_pools:
        return None, None, None, None, None

    candidate_pools.sort(key=lambda item: item[0], reverse=True)
    top_pool = candidate_pools[0]
    top_reserve, top_pool_address, top_pool_created_at, top_token_side = top_pool[0], top_pool[1], top_pool[2], top_pool[3]
    pools_with_creation_date = [pool for pool in candidate_pools if pool[2] is not None]
    earliest_pool = min(pools_with_creation_date, key=lambda item: item[2])
    earliest_reserve, earliest_pool_address, earliest_pool_created_at, earliest_token_side = earliest_pool
    print(f"Selected pool {top_pool_address} with reserve ${top_reserve:,.0f} (token is {top_token_side}); "
          f"earliest pool {earliest_pool_address} created {earliest_pool_created_at} (token is {earliest_token_side})")

    return top_pool_address, earliest_pool_created_at, earliest_pool_address, top_token_side, earliest_token_side


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
def get_ohlcv_history(chain, pool_address, from_timestamp, to_timestamp, token_side):
    network = GECKOTERMINAL_NETWORK_IDS[chain]
    timeframe, aggregate = choose_ohlcv_timeframe_gecko(to_timestamp - from_timestamp)
    print(f"Fetching {timeframe} candles (aggregate={aggregate}) for pool {pool_address} via GeckoTerminal (token={token_side})")

    all_candles = []
    cursor_timestamp = to_timestamp
    while cursor_timestamp > from_timestamp:
        data = query_geckoterminal(
            f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}",
            params={'aggregate': aggregate, 'before_timestamp': cursor_timestamp, 'limit': 1000,
                    'currency': 'usd', 'token': token_side},  # NEW: 'token' param
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


# Flatten OHLCV candles [timestamp, open, high, low, close, volume] into (timestamp, price) pairs, uses 'close' price for each candle
# to minimise possible noise from 'high' prices that may depend on the volume of trade per candle
def transform_candles_to_prices(candles):
    return [(candle[0], candle[4]) for candle in candles]


# Extract the maximum price for a specified range
def get_max_price_in_range(prices, from_timestamp, to_timestamp):
    prices_in_range = [price for timestamp, price in prices if from_timestamp <= timestamp < to_timestamp]
    if not prices_in_range:
        return math.nan
    return max(prices_in_range)


# Determine the end of the quarter window: query time for active tokens and last activity timestamp for dead tokens
def get_window_end_timestamp(latest_block_timestamp, last_activity_timestamp):
    if is_token_live(last_activity_timestamp, latest_block_timestamp):
        return int(latest_block_timestamp.timestamp())
    if last_activity_timestamp is not None:
        return last_activity_timestamp
    # No activity ever recorded, use time of query
    return int(latest_block_timestamp.timestamp())


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
        print(f"Moralis returned {len(data.get('result', []))} candles, cursor={data.get('cursor')}")

        candles = data.get('result', [])
        for candle in candles:
            all_prices.append((parse_moralis_timestamp(candle['timestamp']), candle['close']))

        cursor = data.get('cursor')
        if not cursor or not candles:
            break

    return all_prices, False


# Attempt to fetch data from either Geckoterminal or Moralis
# Since Moralis does not have timestamps on its /pairs endpoint, Geckoterminal is used to get the earliest pool, but
# prices are queried either via Geckoterminal or Moralis, depending on the date of this pool, because Geckoterminal
# gives prices not later than 180 days under demo API key
def try_geckoterminal_or_moralis(chain, token_address, window_end):
    # Chooses a pull with most money (most representative for prices extraction) + the earliest pool to get starting point
    # for prices extraction (before the first pool, there are no prices)
    # Reference: https://docs.coingecko.com/demo/reference/top-pools-contract-address
    top_pool_adr, earliest_pool_created_at, earliest_pool_adr, top_token_side, earliest_token_side = get_top_pool_address(chain, token_address)
    if earliest_pool_adr is None:
        return None, None, None
    window_start = parse_pool_created_at(earliest_pool_created_at)
    age_seconds = int(time.time()) - window_start
    # If the earliest pool is within Geckoterminal historical depth limit, use Geckoterminal for price fetching
    if age_seconds < GECKOTERMINAL_MAX_DEPTH_SECONDS:
        candles, had_failure = get_ohlcv_history(chain, top_pool_adr, window_start, window_end, top_token_side)
        if had_failure or not candles:
            return None, None, None
        # Checks whether full history up to window_start + 5 minutes (fixed source boundary for collection prices) is returned
        # If not, fetch the highest prices available from either top pool, or the earliest pool
        if candles[-1][0] > window_start + 300 and earliest_pool_adr != top_pool_adr:
            print(f"Pool {top_pool_adr} doesn't reach window start, merging in earliest pool {earliest_pool_adr}")
            earliest_candles, earliest_had_failure = get_ohlcv_history(chain, earliest_pool_adr, window_start, window_end, earliest_token_side)
            if not earliest_had_failure and earliest_candles:
                candles += earliest_candles
        prices = transform_candles_to_prices(candles)
        price_source = 'geckoterminal'
    else:
        print(f"Time window is before GeckoTerminal's depth limit, searching the earliest pool {earliest_pool_adr} in Moralis")
        # Get aggregated prices for a Moralis pair
        # Reference: https://docs.moralis.com/data-api/evm/price/ohlc
        prices, had_failure = get_prices_moralis_pair(chain, earliest_pool_adr, window_start, window_end)
        if had_failure or not prices:
            return None, None, None
        price_source = 'moralis'

    return window_start, prices, price_source


# Extract 'MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)' for a live-queried token
# Tries CoinGecko API first. If a queried token is not listed here (result is None)), tries either GeckoTerminal, or Moralis
# depending on how old is a queried token
def get_max_price_quarters_live(chain, token_address, deployment_timestamp, window_end):
    print("MaxPrice (Quarter 1)/(Quarter 2) are calculating...")
    prices = get_prices_coingecko(chain, token_address, deployment_timestamp, window_end)
    if prices is not None:
        result = compute_quarters(prices, deployment_timestamp, window_end, 'coingecko')
        if not (math.isnan(result['MaxPrice (Quarter 1)']) and math.isnan(result['MaxPrice (Quarter 2)'])):
            result['window_start'] = deployment_timestamp
            return result
        print(f"CoinGecko data for {token_address} on {chain} doesn't cover Q1/Q2, trying other sources")
    else:
        print(f"CoinGecko has no data for {token_address} on {chain}, trying other sources")

    window_start, prices, price_source = try_geckoterminal_or_moralis(chain, token_address, window_end)
    if prices is None:
        return {'MaxPrice (Quarter 1)': math.nan, 'MaxPrice (Quarter 2)': math.nan, 'price_source': None, 'window_start': None}

    result = compute_quarters(prices, window_start, window_end, price_source)
    result['window_start'] = window_start
    return result

