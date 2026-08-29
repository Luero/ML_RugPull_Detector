# Runs end-to-end backend test for tokens that are not presented in the dataset (objective 7).
# Every address was verified against news / forensic sources to ensure expected output (see Report for details and references).
# Candidates whose contract address could not be unambiguously established (e.g., Save The Kids, Teddy Doge, MetaSwapGas,
# AnubisDAO, Hope Finance, Blockverse) were excluded for a clear experiment.
#
# Validation set consists of 28 tokens: 9 documented rug pulls (32%) and 19 legitimate tokens of different
# chains, sizes, ages and kinds, including bridges of different sizes (deployments of legitimate projects to "connect" main
# blockchain of deployment and another network) and a tokenized real-world asset. All tokens carry expected labels.
#
# Saves results into two files:
# - a CSV with predictions vs expected labels;
# - a JSON snapshot of extracted features per token (since features can vary over time for live tokens with midpoint shifting towards
#   date of query).
# Snapshots preserve what results were used for a particular round of verification.
#
# Each token costs up to 3 SerpApi searches (free tier is 250/month) and several minutes of throttled
# API calls. Tokens marked 'heavy' had high transfer volume (expensive holder snapshots), so they are skipped unless
# INCLUDE_HEAVY is set.

import json
import os
from datetime import datetime, timezone

import pandas as pd

from app import scan_token
from prediction_module.predictor import Predictor


# Switch to 'True' to include all tokens
INCLUDE_HEAVY = True

OUTPUT_DIR = 'research/validation'

VALIDATION_TOKENS = [
    # Documented rug pulls (expected 'scam')
    {'name': 'Compounder Finance (CP3R)', 'chain': 'ETH', 'address': '0x7ef1081ecc8b5b5b130656a41d4ce4f89dbbcc8c',
     'expected': 'scam', 'heavy': False},
    {'name': 'TurtleDex (TTDX)', 'chain': 'BSC', 'address': '0xb4c35ff2fb98e9b1bba9d574c6879890f551627c',
     'expected': 'scam', 'heavy': False},
    {'name': 'DeFi100 (D100)', 'chain': 'BSC', 'address': '0x9d8aac497a4b8fe697dd63101d793f0c6a6eebb6',
     'expected': 'scam', 'heavy': False},
    {'name': 'Polywhale (KRILL)', 'chain': 'POLYGON', 'address': '0x05089c9ebffa4f0aca269e32056b1b36b37ed71b',
     'expected': 'scam', 'heavy': False},
    {'name': 'WhaleFarm (WHALE)', 'chain': 'BSC', 'address': '0xd07efbcdd7242212ff67372cdb2c9ddaa0290fae',
    'expected': 'scam', 'heavy': False},
    {'name': 'Squid Game (SQUID)', 'chain': 'BSC', 'address': '0x87230146e138d3f296a9a77e497a2a83012e9bc5',
     'expected': 'scam', 'heavy': False},
    {'name': 'Fintoch (FTC)', 'chain': 'BSC', 'address': '0x934e1b6db10d8903cd29952081da8cd925c99dd0',
    'expected': 'scam', 'heavy': False},
    {'name': 'Chibi Finance (CHIBI)', 'chain': 'ARBI', 'address': '0xb3180df05e46f9fcdd589a2023470a9007df01ca',
     'expected': 'scam', 'heavy': False},
    {'name': 'TesseraDAO (TSR)', 'chain': 'BSC', 'address': '0x2f8a0cc5fe14c0cf7f7f95058e6410bae0061fcf',
      'expected': 'scam', 'heavy': False},
    # Legitimate tokens (expected 'normal')
    {'name': 'Maker (MKR)', 'chain': 'ETH', 'address': '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2',
    'expected': 'normal', 'heavy': False},
    {'name': 'dappOS (DOS)', 'chain': 'ETH', 'address': '0x951f086a127e280724fd93ccc543f65065afeb5e',
     'expected': 'normal', 'heavy': False},
    {'name': 'PancakeSwap (CAKE)', 'chain': 'BSC', 'address': '0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82',
     'expected': 'normal', 'heavy': False},
    {'name': 'Aavegotchi (GHST)', 'chain': 'POLYGON', 'address': '0x385eeac5cb85a38a9a07a70c73e0a3271cfb54a7',
     'expected': 'normal', 'heavy': False},
    {'name': 'Treasure (MAGIC)', 'chain': 'ARBI', 'address': '0x539bde0d7dbd336b79148aa742883198bbf60342',
    'expected': 'normal', 'heavy': False},
    {'name': "McDonald's dShare (MCD)", 'chain': 'ARBI', 'address': '0x0c29891dc5060618c779e2a45fbe4808aa5ae6ad',
     'expected': 'normal', 'heavy': False},
    {'name': 'Tellor (TRB, bridged)', 'chain': 'ARBI', 'address': '0xd58d345fd9c82262e087d2d0607624b410d88242',
    'expected': 'normal', 'heavy': False},
    {'name': 'Bitfinex LEO (bridged)', 'chain': 'POLYGON', 'address': '0x06d02e9d62a13fc76bb229373fb3bbbd1101d2fc',
    'expected': 'normal', 'heavy': False},
    {'name': 'Request (REQ), bridged', 'chain': 'POLYGON', 'address': '0xB25e20De2F2eBb4CfFD4D16a55C7B395e8a94762',
     'expected': 'normal', 'heavy': False},
    {'name': 'Chainlink (LINK, bridged)', 'chain': 'POLYGON', 'address': '0xb0897686c545045afc77cf20ec7a532e3120e0f1',
     'expected': 'normal', 'heavy': False},
    {'name': 'Balancer (BAL, bridged)', 'chain': 'ARBI', 'address': '0x040d1edc9569d4bab2d15287dc5a4f10f56a56b8',
    'expected': 'normal', 'heavy': False},
    {'name': 'Dai (DAI, bridged)', 'chain': 'ARBI', 'address': '0xda10009cbd5d07dd0cecc66161fc93d7c9000da1',
     'expected': 'normal', 'heavy': False},
    {'name': 'Mantle (MNT)', 'chain': 'ETH', 'address': '0x3c3a81e81dc49A522A592e7622A7E711c06bf354',
     'expected': 'normal', 'heavy': False},
    {'name': 'Pepe (PEPE, BSC)', 'chain': 'BSC', 'address': '0x25d887ce7a35172c62febfd67a1856f20faebb00',
     'expected': 'normal', 'heavy': False},
    {'name': 'AIOZ Network (AIOZ)', 'chain': 'POLYGON', 'address': '0xe2341718c6c0cbfa8e6686102dd8fbf4047a9e9b',
     'expected': 'normal', 'heavy': False},
    {'name': 'Frax Share (FXS)', 'chain': 'ARBI', 'address': '0x9d2F299715D94d8A7E6F5eaa8E654E8c74a988A7',
     'expected': 'normal', 'heavy': False},
    {'name': 'Gains Network (GNS)', 'chain': 'POLYGON', 'address': '0xe5417af564e4bfda1c483642db72007871397896',
     'expected': 'normal', 'heavy': False},
    {'name': 'Uniswap (UNI)', 'chain': 'ETH', 'address': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
     'expected': 'normal', 'heavy': True},
    {'name': 'Arbitrum (ARB)', 'chain': 'ARBI', 'address': '0x912ce59144191c1204e64559fe8253a0e49e6548',
     'expected': 'normal', 'heavy': True}
]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    predictor = Predictor()
    run_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M')
    results = []
    features_snapshots = {}

    for token in VALIDATION_TOKENS:
        if token['heavy'] and not INCLUDE_HEAVY:
            print(f"...Skipping heavy token {token['name']} (set INCLUDE_HEAVY = True to include)")
            continue
        print(f"\n...Scanning {token['name']} on {token['chain']}")
        result = scan_token(predictor, token['chain'], token['address'])
        features_snapshots[token['address']] = result.get('features') if result['error'] is None else None
        matches_expected = None
        if result['prediction'] is not None:
            matches_expected = result['prediction'] == token['expected']
        results.append({
            'name': token['name'],
            'chain': token['chain'],
            'address': token['address'],
            'expected': token['expected'],
            'prediction': result['prediction'],
            'scam_probability': result['scam_probability'],
            'matches_expected': matches_expected,
            'missing_features_count': len(result['missing_features']) if result['missing_features'] is not None else None,
            'error': result['error']
        })

    results_frame = pd.DataFrame(results)
    results_path = f"{OUTPUT_DIR}/validation_results_{run_timestamp}.csv"
    results_frame.to_csv(results_path, index=False)
    with open(f"{OUTPUT_DIR}/validation_features_{run_timestamp}.json", 'w') as f:
        json.dump(features_snapshots, f, indent=1, default=str)

    print(f"\nSaved to {results_path}")
    print(results_frame[['name', 'chain', 'expected', 'prediction', 'scam_probability', 'matches_expected']].to_string(index=False))
    for expected_label in ('scam', 'normal'):
        subset = results_frame[results_frame['expected'] == expected_label]
        if len(subset):
            matched = int((subset['matches_expected'] == True).sum())
            print(f"expected {expected_label}: {matched}/{len(subset)} match")
    scanned = results_frame[results_frame['prediction'].notna()]
    if len(scanned):
        overall = int(scanned['matches_expected'].sum())
        print(f"overall: {overall}/{len(scanned)} correct")


if __name__ == "__main__":
    main()