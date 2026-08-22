# TODO: comment
import requests
from datetime import datetime, timezone
import time

from feature_extraction_helpers.config import SERP_API_KEY, SERP_BASE_URL


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
def get_osint_features_live(website_url, x_profile_url, trading_start_timestamp, window_end):
    print("Google result counts are calculating...")
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


# TODO: extract website_url/x_profile_url to use as searh_term param for queried tokens


def main():
    website_url = 'pepe.vip'
    x_profile_url = 'twitter.com/pepecoineth'
    trading_start_timestamp = int(datetime(2023, 4, 17, tzinfo=timezone.utc).timestamp())
    window_end = int(time.time())

    result = get_osint_features_live(website_url, x_profile_url, trading_start_timestamp, window_end)
    print(result)


if __name__ == "__main__":
    main()