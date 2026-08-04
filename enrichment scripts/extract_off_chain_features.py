# Extract token name similarity to top-200 projects in form of similarity score.
# Deceptive name similarity is one of OSINT features mentioned in related work as a strong signal of fraud.
#

# TODO: explain methodology of choosing top-200 tokens, algorithm of calculating similarity score




# Files to read and write
INPUT_FILE = '../data/TM-RugPull_with_LP_drain_code_detection.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# '../data/TM-RugPull_with_token_name_similarity.xlsx' was used in original experiment
OUTPUT_FILE = "../data/TM-RugPull_with_token_name_similarity.xlsx"


