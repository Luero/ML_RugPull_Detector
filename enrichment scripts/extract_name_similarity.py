# Extract token name similarity to top-200 projects in form of similarity score.
# Deceptive name similarity is one of OSINT features mentioned in related work as a strong signal of fraud.

# The script uses top-200 snapshots taken from CoinMarketCap historical page (extracted manually by copy-pasting into .csv files).
# Dates for snapshots were picked with consideration of the dataset content (most tokens are from 2021-2024) and market situation:
# so before 2021 snapshots were taken on annual basis (on May). In 2021, 2022 more snapshots were taken, since the market was active
# and top-200 tokens changed faster. Moreover, some market events drove significant changes in ranking (fall of Tera Luna and FTX exchange).
# Thus, to reflect these events, pre- and post- events snapshots were also taken.

# Methodology to count similarity:
# (1) project names and symbols both are assessed separately, and then their scores are combined with heuristic weight application;
# (2) before comparison, each string is normalised to a single lowercase word, then common words like 'finance' or 'token' and words
#     that are commonly used by scammers to misrepresent connection with legitimate assets (like 'new' or 'safe') are stripped to avoid noise;
# (3) Levenstein distance with normalisation is used as string similarity comparison algorithm, since prefixes matter in token names and symbols;
# (4) wrapped versions of legitimate tokens return 0.0 similarity (the pattern is 'w' in the beginning of token symbol);
# (5) self-matches with real tokens are allowed, since to distinguish normal token from scam a label should be used, but than the model will learn
#     incorrect patterns;
# (6) names and symbols are compared against the snapshot which is closest to the project start date, but before the project launch, because
#     token can 'mimic' only coins that exist on time of its launch


import csv
import os
from datetime import datetime

from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook, parse_date
import re


# For some tokens the dataset uses placeholders instead of real symbols
# They were excluded from similarity analysis to avoid noise
SYMBOL_PLACEHOLDERS = {'BEP-20 TOKEN', 'ERC-20 TOKEN', 'ERC20', 'BEP20 TOKEN'}

# 'w' as a prefix to token symbol is a sign that it is a wrapped version of this token, it is legitimate
# A common convention is lower 'w', but dataset has legitimate entries with 'W', so regex is case-insensitive
WRAPPED_TICKER_PREFIX_PATTERN = re.compile(r'^w', re.IGNORECASE)

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

SNAPSHOTS_DIR = '../data/top-200_token_snapshots'
SNAPSHOT_FILENAME_PATTERN = re.compile(r'^(\d{4})_(\d{2})_(\d{2})_top200_snapshot\.csv$')

# Symbol weighted higher than name, since almost identical symbol is a stronger and more misleading signal
PROJECT_NAME_SIMILARITY_WEIGHT = 0.35
SYMBOL_SIMILARITY_WEIGHT = 0.65

# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_LP_drain_code_detection.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_token_name_similarity.xlsx' was used in original experiment
OUTPUT_FILE = "../data/TM-RugPull_with_token_name_similarity.xlsx"



# Pre-process input (project names and symbols) to make them structurally identical (one low-case word)
def normalise_string(string):
    if not string:
        return ''
    # There is a pure numeric entry in the dataset, so convertion is necessary
    string = str(string)
    return NORMALISE_PATTERN.sub('', string.lower())


# Strip common and cover words from a string (a project name, since symbols are relatively unique short identifiers)
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
    # If two empty strings are compared (due to stripping), return 1.0, since
    # it means that they were both combined of common or cover words, so could be potential scam sign
    if longest_length == 0:
        return 1.0
    return 1 - count_levenshtein_distance(dataset_text, snapshot_text) / longest_length


# Compare token symbols from dataset and snapshot of top-200 tokens
def compute_symbol_similarity(dataset_symbol, snapshot_symbol):
    normalised_snapshot_symbol = normalise_string(snapshot_symbol)
    is_wrapped = False
    # Since wrapped tokens are legitimate, returns 0.0 similarity score, if the only difference from top-200 tokens
    # is leading 'w'. Assumes that in this case dataset contains a legitimate top-200 token entry
    if WRAPPED_TICKER_PREFIX_PATTERN.match(dataset_symbol):
        unwrapped_symbol = normalise_string(dataset_symbol.strip()[1:])
        if unwrapped_symbol == normalised_snapshot_symbol:
            is_wrapped = True
            return 0.0, is_wrapped
    return normalise_levenshtein_similarity(normalise_string(dataset_symbol), normalised_snapshot_symbol), is_wrapped


# Compare project name from dataset with project name of top-200 tokens snapshot
def compute_project_name_similarity(dataset_name, snapshot_name):
    prepared_dataset_name = strip_project_name(normalise_string(dataset_name))
    prepared_snapshot_name = strip_project_name(normalise_string(snapshot_name))
    return normalise_levenshtein_similarity(prepared_dataset_name, prepared_snapshot_name)


# Compute final similarity score using weights of each parameter
def compute_combined_similarity(project_name_similarity, symbol_similarity):
    return PROJECT_NAME_SIMILARITY_WEIGHT * project_name_similarity + SYMBOL_SIMILARITY_WEIGHT * symbol_similarity


# Saves all snapshots of top-200 tokens to re-use in comparison, key is date of capture
def load_snapshots(snapshot_dir):
    snapshots = {}
    for filename in os.listdir(snapshot_dir):
        match = SNAPSHOT_FILENAME_PATTERN.match(filename)
        if not match:
            continue
        snapshot_year, snapshot_month, snapshot_day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        with open(os.path.join(snapshot_dir, filename), newline='', encoding='utf-8') as snapshot_file:
            reader = csv.DictReader(snapshot_file)
            snapshots[datetime(snapshot_year, snapshot_month, snapshot_day)] = [(row['name'], row['symbol']) for row in reader]
    return snapshots


# Get snapshot which is the closest to the project's starting date, but before this date (since if a project aim to mimic some
# legitimate token, this token should have been already launched)
def get_relevant_snapshot(snapshots, project_start_date):
    if not snapshots:
        return None
    dates_before = [snapshot_date for snapshot_date in snapshots if snapshot_date <= project_start_date]
    if not dates_before:
        return snapshots[min(snapshots)]
    return snapshots[max(dates_before)]


# Compare project name and symbol from one row with each entry of relevant snapshot, interpret results of comparison
# Allows self-match, since if forcing algorithm to return 0.0 score for all tokens that are labeled as 'normal', the model
# will become biased, and this feature will be deterministic
def compare_and_interpret_final_score(dataset_project_name, dataset_symbol, snapshot):
    # Check for placeholders instead of real symbols
    has_real_symbol = bool(dataset_symbol) and dataset_symbol.strip().upper() not in SYMBOL_PLACEHOLDERS
    best_score = 0.0
    for snapshot_project_name, snapshot_symbol in snapshot:
        project_name_similarity = compute_project_name_similarity(dataset_project_name, snapshot_project_name)
        if has_real_symbol:
            symbol_similarity, is_wrapped = compute_symbol_similarity(dataset_symbol, snapshot_symbol)
            # If a token is wrapped version of legitimate token, overall similarity score is forced to 0.0, since
            # even if it is labeled as scam, similar project name or symbol is not a representative feature in such case
            if is_wrapped:
                final_score = 0.0
            else:
                final_score = compute_combined_similarity(project_name_similarity, symbol_similarity)
        # If there is no symbol in the dataset (only a placeholder), a score is determined by project's name result
        else:
            final_score = project_name_similarity * PROJECT_NAME_SIMILARITY_WEIGHT
        best_score = max(best_score, final_score)
    # Return the score with the best match
    return round(best_score, 4)


# Add similarity score to the .xlsx file
def add_similarity_column(sheet, headings, snapshots):
    project_name_col_idx = headings.index('Project Title')
    symbol_col_idx = headings.index('Sign')
    start_date_col_idx = headings.index('project starting date')

    result_col = sheet.max_column + 1
    sheet.cell(row=1, column=result_col, value='Top200 name similarity')

    for row in sheet.iter_rows(min_row=2):
        dataset_project_name = row[project_name_col_idx].value
        dataset_symbol = row[symbol_col_idx].value
        # There is a pure numeric entry in the dataset, so convertion is necessary
        dataset_symbol = str(dataset_symbol)
        dataset_symbol = '' if dataset_symbol is None else str(dataset_symbol)
        project_start_date = parse_date(row[start_date_col_idx].value)
        if project_start_date is None:
            continue
        snapshot = get_relevant_snapshot(snapshots, project_start_date)
        score = compare_and_interpret_final_score(dataset_project_name, dataset_symbol, snapshot)
        sheet.cell(row=row[0].row, column=result_col, value=score)


def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)
    snapshots = load_snapshots(SNAPSHOTS_DIR)
    add_similarity_column(sheet, headings, snapshots)
    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()