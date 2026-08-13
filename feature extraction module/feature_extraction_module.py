# Extract features from any queried token on Eth, BSC, Arbitrum or Polygon using token contract address
# Is used for feature extraction module of the application. Once extracted, features are submitted to the prediction module,
# where the developed model consume them to make a prediction


# Features to extract (based on features list used by the model from the prediction module
#['MaxPrice (Quarter 1)', 'MaxPrice (Quarter 2)', 'the number of Transactions', 'Token concentration ratio per holder',
# 'Google results for project website (first day)', 'Google results for project x profile (first days)',
# 'Google results for project x profile (duration/2)', 'Holders_12h', 'Holders_24h',
# 'has_contract_swap_patterns', 'has_owner_guard', 'Blockchain Type_POS', 'Blockchain Type_POSA']


from datetime import datetime, timezone
from feature_extraction_helpers.general_onchain_helpers import get_latest_block, query_etherscan, \
    get_deployment_block_and_timestamp
from feature_extraction_helpers.holders_count_helpers import get_holders_snapshots


# Based on TM-RugPull methodology
LIVE_THRESHOLD_HOURS = 72


# Determine whether a token is live by checking the last activity timestamp
def is_token_live(chain, token_address):
    if chain == 'BSC':
        # TODO: implement with NodeReal
        raise NotImplementedError()
    data = query_etherscan(chain, {
        'module': 'account', 'action': 'tokentx', 'contractaddress': token_address,
        'page': 1, 'offset': 1, 'sort': 'desc',
    })
    if data is None or not data.get('result'):
        return False
    last_timestamp = int(data['result'][0]['timeStamp'])
    hours_since = (datetime.now(timezone.utc) - datetime.fromtimestamp(last_timestamp, tz=timezone.utc)).total_seconds() / 3600
    return hours_since <= LIVE_THRESHOLD_HOURS


# Extract project period as required for prediction ('project period (days)')
def get_project_period_days(chain, token_address):
    deployment_block, deployment_timestamp = get_deployment_block_and_timestamp(chain, token_address)
    if deployment_block is None:
        print(f"No deployment block found for {token_address} on {chain}")
        return None

    start_date = datetime.fromtimestamp(deployment_timestamp, tz=timezone.utc)
    if is_token_live(chain, token_address):
        end_date = datetime.now(timezone.utc)
    else:
        data = query_etherscan(chain, {
            'module': 'account', 'action': 'tokentx', 'contractaddress': token_address,
            'page': 1, 'offset': 1, 'sort': 'desc',
        })
        last_timestamp = int(data['result'][0]['timeStamp'])
        end_date = datetime.fromtimestamp(last_timestamp, tz=timezone.utc)

    return (end_date - start_date).days


# Extract 'Holders_12h', 'Holders_24h' features
def get_holders_count_snapshots(chain, token_address):
    latest_arbitrum_block = get_latest_block('ARBI') if chain == 'ARBI' else None
    # Time for snapshots in hours that are used by the model
    time_for_snapshots_hours = (12, 24)
    snapshots = get_holders_snapshots(chain, token_address, time_for_snapshots_hours, latest_arbitrum_block)
    return snapshots





# TODO: a function for each feature + feeding features into the model


def main():
    result = get_project_period_days('POLYGON', '0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8')
    print(result)
    snapshots = get_holders_count_snapshots('POLYGON', '0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8')
    print(snapshots)


if __name__ == "__main__":
    main()