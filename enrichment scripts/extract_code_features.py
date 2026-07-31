from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook






INPUT_FILE = '../data/TM-RugPull_with_holder_count_snapshots.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# was '../data/TM-RugPull_prepared_for_enrichment.xlxs' in original experiment
OUTPUT_FILE = "../data/TM-RugPull_with_LP_drain_code_detection.xlsx"








def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)
    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()