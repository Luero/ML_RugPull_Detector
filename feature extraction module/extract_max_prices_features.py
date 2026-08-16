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
import time
from datetime import datetime, timezone

from feature_extraction_helpers.config import COINGECKO_CHAIN_IDS
from feature_extraction_helpers.general_onchain_helpers import query_coingecko

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
# Reference: https://docs.coingecko.com/reference/contract-address-market-chart-range
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




def main():
    now = int(time.time())
    from_timestamp = now - 30 * 24 * 3600
    to_timestamp = now
    address = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
    prices = get_prices_coingecko('ETH', address, from_timestamp, to_timestamp)
    print(prices)


if __name__ == "__main__":
    main()