# Compute project period for each token from the dataset using project start date and project end date.
# Since project's start and end dates are not informative for any model by themselves, it was decided to use them
# to calculate project period, which could have predictive power to detect rug-pulls, since projects that live longer
# are less likely to be fraudulent.


from xlxs_helpers.io_helpers import load_file, get_headings, save_workbook, parse_date

INPUT_FILE = '../data/TM-RugPull_prepared_for_enrichment.xlsx'
# A placeholder file to safe from re-writing anything already computed,
# was '../data/TM-RugPull_prepared_for_enrichment.xlxs' in original experiment
OUTPUT_FILE = "../data/placeholder.xlsx"


# Calculate duration of a project in days
def compute_project_period(start, end):
    if start is None or end is None:
        return None
    return (end - start).days


# Adds a new column with project period value in the end of the table
def add_project_period_column(sheet, headings):
    start_col_idx = headings.index('project starting date')
    end_col_idx = headings.index('project end date')
    period_col_number = len(headings) + 1

    sheet.cell(row=1, column=period_col_number, value='project period (days)')

    for row in sheet.iter_rows(min_row=2):
        start = parse_date(row[start_col_idx].value)
        end = parse_date(row[end_col_idx].value)
        period = compute_project_period(start, end)
        if period is None:
            print(f"Row {row[0].row}: could not compute period")
            continue
        sheet.cell(row=row[0].row, column=period_col_number, value=period)


def main():
    workbook, sheet = load_file(INPUT_FILE)
    headings = get_headings(sheet)
    add_project_period_column(sheet, headings)
    save_workbook(workbook, OUTPUT_FILE)


if __name__ == "__main__":
    main()
