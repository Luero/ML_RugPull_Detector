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
COVER_WORDS = ['baby', 'safe', 'mini', 'new', 'classic']

# Build compiled regex for each word in order to cover all possible common suffix / prefix occurrences
def build_prefix_suffix_pattern(word):
    escaped = re.escape(word)
    return re.compile(rf'^{escaped}|{escaped}$')

COMMON_WORD_PATTERNS = [build_prefix_suffix_pattern(word) for word in COMMON_SUFFIX_OR_PREFIX]
# Sometimes scammers put version number near token name to mis-represent it as a new version of well-known project
# Based on TM-RugPull dataset naming patterns
COVER_PATTERNS = [build_prefix_suffix_pattern(word) for word in COVER_WORDS] + [re.compile(r'v\d+$')]

COMBINED_PATTERNS_TO_STRIP = COVER_PATTERNS + COMMON_WORD_PATTERNS

# All project names and symbols are normalised before comparing similarity (remove spaces, punctuation)
# to make names like 'safeETH', 'Safe ETH' and 'SAFE-eth' identical
NORMALISE_PATTERN = re.compile(r'[^a-z0-9]')

# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_LP_drain_code_detection.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_token_name_similarity.xlsx' was used in original experiment
OUTPUT_FILE = "../data/TM-RugPull_with_token_name_similarity.xlsx"



# Pre-process input (project names and symbols) to make them structurally identical (one low-case word)
def normalise_string(string):
    if not string:
        return ''
    return NORMALISE_PATTERN.sub('', string.lower())


# Strip common and cover words from a string (a project name, since symbols does not stripping, they are relatively unique
# short identifiers
def strip_project_name(project_name):
    stripped_project_name = project_name
    is_changed = True
    # Loops over stripped version to detect nesting common or cover words (like 'safebabyETH')
    while is_changed:
        is_changed = False
        for pattern in COMBINED_PATTERNS_TO_STRIP:
            new_stripped = pattern.sub('', stripped_project_name)
            if new_stripped != stripped_project_name:
                stripped_project_name = new_stripped
                is_changed = True
    return stripped_project_name


# Levenshtein distance algorithm to compute similarity score was chosen, since it works well on relatively small strings,
# where prefixes also matter (in comparison with Jaro-Winkler algorithm which was also considered)
# Reference: https://medium.com/data-science-collective/deep-dive-into-string-similarity-from-edit-distance-to-fuzzy-matching-theory-and-practice-in-68e214c0cb1d
def count_levenshtein_distance(dataset_text, snapshot_text):
    # Identical strings, no need to count distances
    if dataset_text == snapshot_text:
        return 0
    dataset_text_length = len(dataset_text)
    snapshot_text_length = len(snapshot_text)
    # Compare with empty string results in each char to be inserted or deleted (= length of another string)
    if dataset_text_length == 0:
        return snapshot_text_length
    if snapshot_text_length == 0:
        return dataset_text_length

    previous_edit_row = list(range(snapshot_text_length + 1))
    for dataset_text_index, dataset_text_char in enumerate(dataset_text, start=1):
        current_edit_row = [dataset_text_index] + [0] * snapshot_text_length
        for snapshot_text_index, snapshot_text_char in enumerate(snapshot_text, start=1):
            deletion_cost = previous_edit_row[snapshot_text_index] + 1
            insertion_cost = current_edit_row[snapshot_text_index - 1] + 1
            # No extra cost if the characters already match. Otherwise, 1 for substitution
            substitution_cost = previous_edit_row[snapshot_text_index - 1] + (dataset_text_char != snapshot_text_char)
            current_edit_row[snapshot_text_index] = min(deletion_cost, insertion_cost, substitution_cost)
        previous_edit_row = current_edit_row

    return previous_edit_row[snapshot_text_length]


# To compare distances for pairs of different lengths normalisation is applied
def normalise_levenshtein_similarity(dataset_text, snapshot_text):
    longest_length = max(len(dataset_text), len(snapshot_text))
    return 1 - count_levenshtein_distance(dataset_text, snapshot_text) / longest_length



# TODO: read and parse .csv



def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)

    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()