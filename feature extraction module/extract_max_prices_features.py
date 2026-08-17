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

import math
import time
from datetime import datetime, timezone

from feature_extraction_helpers.config import COINGECKO_CHAIN_IDS, GECKOTERMINAL_NETWORK_IDS
from feature_extraction_helpers.general_onchain_helpers import query_coingecko, get_last_activity_timestamp, \
    is_token_live, get_deployment_block_and_timestamp, get_latest_block_with_timestamp, query_geckoterminal

# Thresholds to pick OHLCV candle resolution based on window length
# More granularity for short living tokens (to catch rug-pull), increasing for long-living projects due to
# efficiency reasons and API limits
# Reference: https://docs.coingecko.com/reference/pool-ohlcv-contract-address
OHLCV_THRESHOLDS_SECONDS = (
    (2 * 24 * 3600, 'minute', 15),   # for window <= 2 days: 15-minute candles
    (60 * 24 * 3600, 'hour', 1),     # for window <= 60 days: 1-hour candles
    (float('inf'), 'day', 1),        # for anything longer: daily candles
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
# to query prices it is necessary to find related pools
# Cached every 60 seconds for Demo plan
# Reference: https://docs.coingecko.com/demo/reference/top-pools-contract-address
def get_top_pool_address(chain, token_address):
    network = GECKOTERMINAL_NETWORK_IDS[chain]
    data = query_geckoterminal(f"/networks/{network}/tokens/{token_address}/pools")
    if data is None or not data.get('data'):
        print(f"No pools found for {token_address} on {chain}")
        return None, None

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
        return None, None

    candidate_pools.sort(key=lambda item: item[0], reverse=True)
    top_reserve, top_pool_address, _ = candidate_pools[0]
    earliest_pool_created_at = min(item[2] for item in candidate_pools if item[2] is not None)
    print(f"Selected pool {top_pool_address} with reserve ${top_reserve:,.0f}; earliest pool created {earliest_pool_created_at}")

    return top_pool_address, earliest_pool_created_at


# Convert GeckoTerminal's ISO 8601 timestamp into a unix timestamp
def parse_pool_created_at(pool_created_at):
    return int(datetime.strptime(pool_created_at, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())


# Determine a time window depending on inspected period
def choose_ohlcv_timeframe(window_seconds):
    for max_seconds, timeframe, aggregate in OHLCV_THRESHOLDS_SECONDS:
        if window_seconds <= max_seconds:
            return timeframe, aggregate





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


# Extract 'MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)' for a live-queried token
# Tries CoinGecko API first. If a queried token is not listed here (code 404), tries GeckoTerminal with pool-resolution
# TODO: add Geckoterminal once tested
def get_max_price_quarters_live(chain, token_address, deployment_timestamp, latest_block_timestamp):
    print("MaxPrice (Quarter 1)/(Quarter 2) are calculating...")
    window_end = get_window_end_timestamp(chain, token_address, latest_block_timestamp)

    prices = get_prices_coingecko(chain, token_address, deployment_timestamp, window_end)
    if prices is not None:
        window_start = deployment_timestamp
        price_source = 'coingecko'
    else:
        print(f"CoinGecko has no data for {token_address} on {chain}, trying GeckoTerminal")
        window_start, prices = try_geckoterminal_source(chain, token_address, window_end)
        if prices is None:
            return {'MaxPrice (Quarter 1)': math.nan, 'MaxPrice (Quarter 2)': math.nan}
        price_source = 'geckoterminal'

    quarter_length_seconds = (window_end - window_start) / 4
    if quarter_length_seconds <= 0:
        print(f"Negative window for {token_address} on {chain}, calculation mistake")
        return {'MaxPrice (Quarter 1)': math.nan, 'MaxPrice (Quarter 2)': math.nan, 'price_source': price_source}

    q1_start = window_start
    q1_end = window_start + quarter_length_seconds
    q2_end = window_start + 2 * quarter_length_seconds

    return {
        'MaxPrice (Quarter 1)': get_max_price_in_range(prices, q1_start, q1_end),
        'MaxPrice (Quarter 2)': get_max_price_in_range(prices, q1_end, q2_end),
        'price_source': price_source,
    }



def main():
    address = '0x100acD9FcD8E0FF80A6595B66fdABe93184Aa100'
    chain = 'ETH'
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, address)
    latest_block, latest_block_timestamp = get_latest_block_with_timestamp(chain)
    prices = get_max_price_quarters_live(chain, address, deployment_timestamp, latest_block_timestamp)
    print(prices)


if __name__ == "__main__":
    main()