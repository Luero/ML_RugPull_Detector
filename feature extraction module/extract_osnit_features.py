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


# TODO: extract website_url/x_profile_url to use as searh_term param for queried tokens


def main():
    website_url = 'pepe.vip'
    x_profile_url = 'twitter.com/pepecoineth'
    trading_start_timestamp = int(datetime(2023, 4, 17, tzinfo=timezone.utc).timestamp())
    test_date = int(datetime(2025, 4, 17, tzinfo=timezone.utc).timestamp())     # to test 1-day window does not return 0
    window_end = int(time.time())

    result = get_google_result_count(website_url, trading_start_timestamp)
    print(result)


if __name__ == "__main__":
    main()