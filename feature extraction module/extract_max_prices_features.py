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


# Thresholds to pick OHLCV candle resolution based on window length
# More granularity for short living tokens (to catch rug-pull), increasing for long-living projects due to
# efficiency reasons and API limits
# Reference: https://docs.coingecko.com/reference/pool-ohlcv-contract-address
OHLCV_THRESHOLDS_SECONDS = (
    (2 * 24 * 3600, 'minute', 15),   # for window <= 2 days: 15-minute candles
    (60 * 24 * 3600, 'hour', 1),     # for window <= 60 days: 1-hour candles
    (float('inf'), 'day', 1),        # for anything longer: daily candles
)