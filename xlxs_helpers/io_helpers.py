# A custom library with general helper functions for loading and saving .xlxs file
# to reuse in all data enrichment scripts

# OpenPyXL is used here to preserve hyperlinks in the dataset file.

from openpyxl import load_workbook
from datetime import datetime

# Load .xlsx file using OpenPyXL
# Returns workbook and sheet from .xlcx file
def load_file (file):
    workbook = load_workbook(file, data_only=True)
    sheet = workbook['Sheet1']
    return workbook, sheet


# Save a workbook with amenmdnments to a new .xlxs file
def save_workbook(workbook, output_file):
    workbook.save(output_file)
    print(f"Saved to {output_file}")


# Extract a header row as a list
def get_headings(sheet):
    return [c.value for c in sheet[1]]


# Parse a cell that supposed to be a date and attempt to extract it in datetime format
def parse_date(date):
    if date is None:
        return None
    if isinstance(date, datetime):
        return date
    try:
        return datetime.strptime(str(date), '%Y-%m-%d')
    except ValueError:
        print(f"Could not parse date: {date}")
        return None