# Extract token name similarity to top-200 projects in form of similarity score.
# Deceptive name similarity is one of OSINT features mentioned in related work as a strong signal of fraud.
#
# TODO: explain methodology of choosing top-200 tokens, algorithm of calculating similarity score
# Dates to get top-200 token snapshots
# 05.2014
# 05.2015
# 05.2016
# 05.2017
# 05.2018
# 05.2019
# 05.2020
# 01.2021 – pre-bull run
# 11.2021 – bull run
# 01.2022 – before Tera Luna
# 05.2022 – after Luna (late dates)
# 11.2022 – after FTX (late dates)
# 05.2023
# 05.2024


from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook
import re


# For some tokens the dataset uses placeholders instead of real symbols
# They were excluded from similarity analysis to avoid noise
SYMBOL_PLACEHOLDERS = {'BEP-20 TOKEN', 'ERC-20 TOKEN', 'ERC20', 'BEP20 TOKEN'}

# 'w' as a prefix to token symbol is a sign that it is a wrapped version of this token, it is legitimate
WRAPPED_TICKER_PREFIX_PATTERN = re.compile(r'^w(?=[A-Z])')

# Strings that could appear in both scam and legitimate tokens as suffixes, prefixes or separate words in project names
COMMON_SUFFIX_OR_PREFIX = ['finance', 'crypto', 'token', 'coin', 'fork', 'play', 'cash', 'fund', 'trade', 'swap', 'tech',
                           'ai', 'reward', 'protocol', 'network', 'dao', 'labs', 'foundation', 'chain', 'ecosystem']

# Strings that scammers sometimes add as prefixes to well-known names to false represent relation to these well-known projects
# Based on TM-RugPull dataset naming patterns
COVER_WORDS = ['baby', 'safe', 'mini']

# Sometimes scammers put version number near token name to mis-represent it as a new version of well-known project
# Based on TM-RugPull dataset naming patterns
VERSION_PATTERNS = [
    re.compile(r'\b\d+\.0\b'),
    re.compile(r'\bv\d+\b', re.IGNORECASE),
    re.compile(r'\(new\)', re.IGNORECASE),
    re.compile(r'\bclassic\b', re.IGNORECASE),
]

# Build compiled regex for each word in order to cover all possible common suffix / prefix occurrences
def build_word_pattern(word):
    escaped = re.escape(word)
    return re.compile(rf'^{escaped}|{escaped}$|\b{escaped}\b', re.IGNORECASE)

COMMON_WORD_PATTERNS = [build_word_pattern(word) for word in COMMON_SUFFIX_OR_PREFIX]
COVER_PATTERNS = [build_word_pattern(word) for word in COVER_WORDS]

# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_LP_drain_code_detection.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_token_name_similarity.xlsx' was used in original experiment
OUTPUT_FILE = "../data/TM-RugPull_with_token_name_similarity.xlsx"


# TODO: choose and implement an algorithm for string comparison:
# TODO: https://medium.com/data-science-collective/deep-dive-into-string-similarity-from-edit-distance-to-fuzzy-matching-theory-and-practice-in-68e214c0cb1d






def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)

    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()