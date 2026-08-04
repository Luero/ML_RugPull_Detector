# Extract token name similarity to top-200 projects in form of similarity score.
# Deceptive name similarity is one of OSINT features mentioned in related work as a strong signal of fraud.
#
from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook

# TODO: explain methodology of choosing top-200 tokens, algorithm of calculating similarity score


import re


# For some tokens the dataset uses placeholders instead of real symbols
# They were excluded from similarity analysis to avoid noise
SYMBOL_PLACEHOLDERS = {'BEP-20 TOKEN', 'ERC-20 TOKEN', 'ERC20', 'BEP20 TOKEN'}

# TODO: pre-process project names (strip 'Finance', 'Crypto', 'Token', 'fork', 'play', 'coin', 'cash', 'protocol', 'network', 'labs', 'foundation', 'DAO', 'chain', 'ecosystem',
# TODO: 'fund', 'trade, 'swap', 'tech, 'AI' (with boundaries), 'reward', 'w' (wrapped - a common prefix for legitimate wrapped tokens, specific pattern for symbols)
# Strings that could appear in both scam and legitimate tokens as suffixes, prefixes or separate words in project names
COMMON_PARTS = [
    re.compile(r'\bfinance\b', re.IGNORECASE),
    re.compile(r'\bcrypto\b', re.IGNORECASE),
    re.compile(r'\btoken\b', re.IGNORECASE),
    re.compile(r'\bcoin\b', re.IGNORECASE),
    re.compile(r'\bfork\b', re.IGNORECASE),
    re.compile(r'\bplay\b', re.IGNORECASE),
    re.compile(r'\bcash\b', re.IGNORECASE),
    re.compile(r'\bfund\b', re.IGNORECASE),
    re.compile(r'\btrade\b', re.IGNORECASE),
    re.compile(r'\bswap\b', re.IGNORECASE),
    re.compile(r'\btech\b', re.IGNORECASE),
    # TODO: reduce false-positiveness
    re.compile(r'\bai\b', re.IGNORECASE),
    re.compile(r'\breward\b', re.IGNORECASE),
    re.compile(r'\bprotocol\b', re.IGNORECASE),
    re.compile(r'\bnetwork\b', re.IGNORECASE),
    re.compile(r'\bdao\b', re.IGNORECASE),
    re.compile(r'\blabs\b', re.IGNORECASE),
    re.compile(r'\bfoundation\b', re.IGNORECASE),
    re.compile(r'\bchain\b', re.IGNORECASE),
    re.compile(r'\becosystem\b', re.IGNORECASE),
]

# TODO: choose and implement an algorithm for string comparison:
# TODO: https://medium.com/data-science-collective/deep-dive-into-string-similarity-from-edit-distance-to-fuzzy-matching-theory-and-practice-in-68e214c0cb1d


# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_LP_drain_code_detection.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_token_name_similarity.xlsx' was used in original experiment
OUTPUT_FILE = "../data/TM-RugPull_with_token_name_similarity.xlsx"





def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)

    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()