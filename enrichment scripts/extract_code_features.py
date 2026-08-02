# Extract code-based features from source code files stored locally in .txt format (one file for each project from the
# dataset).
# .txt files are named according to row numbers in original version of the dataset.
# To map them with relevant projects, a composite key is used to avoid confusion, since the dataset has been cleaned from
# duplicate values.

# TODO: explain what features are extracted from the source code


from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook
import pandas as pd
import os



# Original dataset file
ORIGINAL_FILE = '../data/TM-RugPull_original.xlsx'
# Local directory with contract code files
SOURCE_CODE_DIR = '../data/SOURCE CODE'

INPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'
OUTPUT_FILE = "../data/TM-RugPull_with_LP_drain_code_detection.xlsx"




# Build a composite key to use for mapping projects to relevant rows in original dataset and then to .txt files
# Using simple a project title could fail, because there are projects with identical names
# Uses values for 'Project Title' and 'project end date'
def build_composite_key(row):
    return f"{row['Project Title']}|{row['project end date']}"


# Map each composite key in original file to its row number.
def map_key_to_original_row(original):
    result = {}
    for i, row in original.iterrows():
        key = build_composite_key(row)
        excel_row_number = i + 2              # 1 row in .xlxs is a heading, pandas indexing is from 0
        result.setdefault(key, []).append(excel_row_number)
    return result


# Resolve rows of current version of the dataset to its original file number
def resolve_source_file_number(row, mapping_result):
    key = build_composite_key(row)
    matches = mapping_result.get(key)
    if not matches:
        print(f"No original row match for: {row['Project Title']}")
        return None
    if len(matches) > 1:
        print(f"Ambiguous match for {row['Project Title']}: candidates {matches}")
        return None
    return matches[0]


# Build the path to files where contract code is located
def build_path_to_source_code_file(original_row_number):
    filename = f"{original_row_number}.txt"
    return os.path.join(SOURCE_CODE_DIR, filename)


# Load source code .txt file for a particular row using row number and mapping result
def load_source_code_for_row(row, mapping_result):
    file_number = resolve_source_file_number(row, mapping_result)
    if file_number is None:
        return None
    path = build_path_to_source_code_file(file_number)
    if not os.path.isfile(path):
        print(f"Source file missing: {path}")
        return None
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as code_file:
            return code_file.read()
    except OSError as e:
        print(f"Could not read {path}: {e}")
        return None



def main():
     original = pd.read_excel(ORIGINAL_FILE)
     cleaned = pd.read_excel(INPUT_FILE)
     mapping_result = map_key_to_original_row(original)
     for i, row in cleaned.iterrows():
        match = resolve_source_file_number(row, mapping_result)
        print(f"{row['Project Title']} | {row['project end date']} --> source file: {match}.txt")

    # workbook, sheet = load_file(INPUT_FILE)
    # headings = get_headings(sheet)
    # save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()