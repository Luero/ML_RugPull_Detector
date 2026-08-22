# TODO: comment
import requests
from datetime import datetime, timezone
import time

from feature_extraction_helpers.config import SERP_API_KEY, SERP_BASE_URL, DEXSCREENER_CHAIN_IDS, MORALIS_CHAIN_IDS, \
    COINGECKO_CHAIN_IDS
from feature_extraction_helpers.general_extraction_helpers import query_dexscreener, query_moralis, query_coingecko


# Features to extract (based on features list used by the model from the prediction module
# 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# 'Google results for project x profile (duration/2)'


# General function to query SerpApi's Google search engine
# Reference: https://serpapi.com/search-api
def query_serpapi(search_term, date_range=None):
    params = {'engine': 'google', 'q': search_term, 'api_key': SERP_API_KEY}
    if date_range is not None:
        cd_min, cd_max = date_range
        params['tbs'] = f"cdr:1,cd_min:{cd_min},cd_max:{cd_max}"

    response = requests.get(SERP_BASE_URL, params=params, timeout=30)
    if response.status_code != 200:
        print(f"HTTP error {response.status_code} for SerpApi query '{search_term}'")
        return None

    data = response.json()
    if 'error' in data:
        print(f"SerpApi error for '{search_term}': {data['error']}")
        return None

    return data


# Get Google's total results for a search term for a particular date
def get_google_result_count(search_term, target_timestamp):
    target_date = convert_cdr_date(target_timestamp)
    data = query_serpapi(search_term, date_range=(target_date, target_date))

    if data is None:
        return None

    total_results = data.get('search_information', {}).get('total_results')
    if total_results is None:
        print(f"No total_results field for '{search_term}'")
        return None

    return int(total_results)


# Convert timestamp into SerpApi's expected date format (MM/DD/YYYY)
def convert_cdr_date(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime('%m/%d/%Y')


# Calculate midpoint timestamp between the start of trading activity (start date as in RugPull methodology)
# and end of observation window (query time for live tokens, last activity for dead ones)
def get_midpoint_timestamp(trading_start_timestamp, window_end):
    return int(trading_start_timestamp + (window_end - trading_start_timestamp) / 2)


# Extract 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# and 'Google results for project x profile (duration/2)' for a live-queried token
# trading_start_timestamp is the first trading activity (earliest pool/pair creation), consistent to window_start for price extraction
# If not found, use deployment_timestamp
def get_osint_features_live(chain, token_address, trading_start_timestamp, window_end):
    print("Google result counts are calculating...")
    website_url, x_profile_url = get_project_socials(chain, token_address)
    print("Querying SerpAPI...")
    midpoint_timestamp = get_midpoint_timestamp(trading_start_timestamp, window_end)
    website_first_day = None
    if website_url:
        website_first_day = get_google_result_count(website_url, trading_start_timestamp)
    else:
        print("No website URL available")

    x_profile_first_day = None
    x_profile_midpoint = None
    if x_profile_url:
        x_profile_first_day = get_google_result_count(x_profile_url, trading_start_timestamp)
        x_profile_midpoint = get_google_result_count(x_profile_url, midpoint_timestamp)
    else:
        print("No X profile URL available")

    return {
        'Google results for project website (first day)': website_first_day,
        'Google results for project x profile (first days)': x_profile_first_day,
        'Google results for project x profile (duration/2)': x_profile_midpoint
    }


# TODO: Do I need to reconstruct X_profile url (with x.com) or handle is enough?
# Extract token's website and X profile URL on DEXScreener
# https://docs.dexscreener.com/api/reference#get-token-pairs-v1-chainid-tokenaddress
def get_project_socials_dexscreener(chain, token_address):
    print("Trying DEXScreener for socials resolution...")
    dexscreener_chain = DEXSCREENER_CHAIN_IDS.get(chain)
    if dexscreener_chain is None:
        return None, None

    data = query_dexscreener(f"/token-pairs/v1/{dexscreener_chain}/{token_address}")
    print(data)
    if data is None or not data:
        return None, None

    website_url = None
    x_profile_url = None
    for pair in data:
        info = pair.get('info', {})
        if website_url is None:
            websites = info.get('websites', [])
            if websites:
                website_url = websites[0].get('url')
        if x_profile_url is None:
            socials = info.get('socials', [])
            match = next((s.get('handle') for s in socials if s.get('platform') in ('twitter', 'x')), None)
            if match:
                x_profile_url = f"https://x.com/{match}"
        if website_url and x_profile_url:
            break

    return website_url, x_profile_url


# Extract token's website and X profile URL via Moralis
# Reference: https://docs.moralis.com/data-api/evm/token/metadata/token-metadata
def get_project_socials_moralis(chain, token_address):
    print("Trying Moralis for socials resolution...")
    moralis_chain = MORALIS_CHAIN_IDS.get(chain)
    if moralis_chain is None:
        return None, None
    data = query_moralis(f"/erc20/metadata", params={'chain': moralis_chain, 'addresses': [token_address]})
    if data is None or not data:
        return None, None
    links = data[0].get('links', {}) if isinstance(data, list) else data.get('links', {})
    website_url = links.get('website') or None
    twitter = links.get('twitter') or None
    x_profile_url = f"https://x.com/{twitter}" if twitter else None

    return website_url, x_profile_url


# Extract token's website and X profile URL via CoinGecko
# Reference: https://docs.coingecko.com/reference/coins-contract-address
def get_project_socials_coingecko(chain, token_address):
    print("Trying CoinGecko for socials resolution...")
    coingecko_chain = COINGECKO_CHAIN_IDS.get(chain)
    if coingecko_chain is None:
        return None, None
    data = query_coingecko(f"/coins/{coingecko_chain}/contract/{token_address}")
    if data is None:
        return None, None

    links = data.get('links', {})
    homepages = links.get('homepage', [])
    website_url = next((url for url in homepages if url), None)
    twitter_handle = links.get('twitter_screen_name') or None
    x_profile_url = f"https://x.com/{twitter_handle}" if twitter_handle else None

    return website_url, x_profile_url


# Extract token's website and X profile URL, trying sources in order: Moralis -> CoinGecko -> DEXScreener
# to make retrieval as stable as possible, since all sources have different coverage
def get_project_socials(chain, token_address):
    website_url = None
    x_profile_url = None
    for source in (get_project_socials_moralis, get_project_socials_coingecko, get_project_socials_dexscreener):
        if website_url and x_profile_url:
            break
        resolved_website, resolved_x_profile = source(chain, token_address)
        if website_url is None and resolved_website:
            website_url = resolved_website
        if x_profile_url is None and resolved_x_profile:
            x_profile_url = resolved_x_profile
    if website_url is None and x_profile_url is None:
        print(f"No socials resolved for {token_address} on {chain} from any source")

    return website_url, x_profile_url


# TODO: use window_start from get_max_price_quarters_live when aggregating into one module
def main():
    chain, token_address = 'BSC', '0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00'
    print(chain, token_address)
    trading_start_timestamp = int(datetime(2023, 4, 17, tzinfo=timezone.utc).timestamp())
    window_end = int(time.time())

    result = get_osint_features_live(chain, token_address, trading_start_timestamp, window_end)
    print(result)


if __name__ == "__main__":
    main()