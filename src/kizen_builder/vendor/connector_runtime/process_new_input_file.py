#!/usr/bin/env python3
import csv
import json
import os
import sys
from datetime import datetime

from .script_runner import (
    dedupe_and_normalize_headers,
    detect_encoding_from_buffer,
    load_workbook,
    process_excel_to_csv,
    process_excel_to_csvs,
    process_zip_to_csvs,
)

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}
ZIP_EXTENSIONS = {".zip"}


def process_csv_file(input_path, output_path):
    with open(input_path, "rb") as f:
        sample = f.read(65536)
    encoding = detect_encoding_from_buffer(sample)

    with open(input_path, "r", encoding=encoding, errors="replace", newline="") as infile:
        reader = csv.reader(infile)
        headers = next(reader)
        new_headers = dedupe_and_normalize_headers(headers)

        with open(output_path, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.writer(outfile, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(new_headers)
            for row in reader:
                if row:
                    writer.writerow(row)

    return headers, new_headers


def process_new_input_file(input_path, workdir=None):
    # `workdir` is the connector working directory (holds __config.json + data/).
    # Upstream derived it from __file__; parametrized here so the vendored copy
    # can run against any pulled-package directory. See PROVENANCE.md.
    script_dir = workdir or os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "__config.json")
    data_dir = os.path.join(script_dir, "data")

    if not os.path.exists(config_path):
        print(f"Error: __config.json not found at {config_path}")
        sys.exit(1)

    os.makedirs(data_dir, exist_ok=True)

    input_filename = os.path.basename(input_path)
    name_part, ext = os.path.splitext(input_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    is_excel = ext.lower() in EXCEL_EXTENSIONS
    is_zip = ext.lower() in ZIP_EXTENSIONS

    with open(config_path, "r") as f:
        config = json.load(f)

    if is_zip:
        print(f"Processing ZIP file: {input_path}")
        temp_dir = os.path.join(data_dir, f"_temp_{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        try:
            results = process_zip_to_csvs(input_path, temp_dir)
            original_tables = config.get("input_tables", [])

            for idx, result in enumerate(results):
                original_name = os.path.splitext(result["file_name"])[0]
                timestamped_filename = f"{original_name}_{timestamp}.csv"
                timestamped_path = os.path.join(data_dir, timestamped_filename)

                os.rename(result["output_path"], timestamped_path)

                matching_table = next((t for t in original_tables if t.get("page_idx") == idx), None)
                if matching_table:
                    matching_table["file_path"] = f"data/{timestamped_filename}"
                    matching_table["name"] = timestamped_filename
                    print(
                        f"  Updated table '{matching_table['table_name']}' (page_idx={idx}) -> data/{timestamped_filename}"
                    )
                else:
                    config["input_tables"].append(
                        {
                            "page_idx": idx,
                            "name": timestamped_filename,
                            "table_name": result["table_name"],
                            "file_path": f"data/{timestamped_filename}",
                            "columns_mapping": [{"col": col, "type": "str"} for col in result["new_headers"]],
                        }
                    )
                    print(f"  Added new table '{result['table_name']}' -> data/{timestamped_filename}")

                if result["headers"] != result["new_headers"]:
                    print("    Headers modified:")
                    for old, new in zip(result["headers"], result["new_headers"]):
                        if old != new:
                            print(f"      '{old}' -> '{new}'")
        finally:
            if os.path.exists(temp_dir):
                import shutil

                shutil.rmtree(temp_dir)

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        print(f"\nProcessed {len(results)} CSV files from ZIP")
        print(f"Updated {min(len(results), len(original_tables))} existing tables")
    else:
        original_tables = config.get("input_tables", [])
        if not original_tables:
            print("Error: No input_tables found in __config.json")
            sys.exit(1)

        if is_excel:
            workbook = load_workbook(input_path)
            num_sheets = len(workbook.sheet_names)

            if num_sheets > 1:
                print(f"Processing multi-sheet Excel file: {input_path} ({num_sheets} sheets)")
                temp_dir = os.path.join(data_dir, f"_temp_{timestamp}")
                os.makedirs(temp_dir, exist_ok=True)
                try:
                    results = process_excel_to_csvs(input_path, temp_dir)

                    for idx, result in enumerate(results):
                        original_name = os.path.splitext(result["file_name"])[0]
                        timestamped_filename = f"{original_name}_{timestamp}.csv"
                        timestamped_path = os.path.join(data_dir, timestamped_filename)

                        os.rename(result["output_path"], timestamped_path)

                        matching_table = next((t for t in original_tables if t.get("page_idx") == idx), None)
                        if matching_table:
                            matching_table["file_path"] = f"data/{timestamped_filename}"
                            matching_table["name"] = timestamped_filename
                            print(
                                f"  Updated table '{matching_table['table_name']}' (page_idx={idx}) -> data/{timestamped_filename}"
                            )
                        else:
                            config["input_tables"].append(
                                {
                                    "page_idx": idx,
                                    "name": timestamped_filename,
                                    "table_name": result["table_name"],
                                    "file_path": f"data/{timestamped_filename}",
                                    "columns_mapping": [{"col": col, "type": "str"} for col in result["new_headers"]],
                                }
                            )
                            print(f"  Added new table '{result['table_name']}' -> data/{timestamped_filename}")

                        if result["headers"] != result["new_headers"]:
                            print("    Headers modified:")
                            for old, new in zip(result["headers"], result["new_headers"]):
                                if old != new:
                                    print(f"      '{old}' -> '{new}'")
                finally:
                    if os.path.exists(temp_dir):
                        import shutil

                        shutil.rmtree(temp_dir)

                with open(config_path, "w") as f:
                    json.dump(config, f, indent=2)

                print(f"\nProcessed {len(results)} sheets from Excel file")
                print(f"Updated {min(len(results), len(original_tables))} existing tables")
            else:
                print(f"Processing single-sheet Excel file: {input_path}")
                output_filename = f"{name_part}_{timestamp}.csv"
                output_path = os.path.join(data_dir, output_filename)
                headers, new_headers = process_excel_to_csv(input_path, output_path)

                original_tables[0]["file_path"] = f"data/{output_filename}"
                original_tables[0]["name"] = output_filename

                with open(config_path, "w") as f:
                    json.dump(config, f, indent=2)

                print(f"Processed: {input_path} -> {output_path}")
                print(
                    f"Updated table '{original_tables[0]['table_name']}' file_path and name to: data/{output_filename}"
                )
                if headers != new_headers:
                    print("Headers modified:")
                    for old, new in zip(headers, new_headers):
                        if old != new:
                            print(f"  '{old}' -> '{new}'")
        else:
            print(f"Processing CSV file: {input_path}")
            output_filename = f"{name_part}_{timestamp}.csv"
            output_path = os.path.join(data_dir, output_filename)
            headers, new_headers = process_csv_file(input_path, output_path)

            original_tables[0]["file_path"] = f"data/{output_filename}"
            original_tables[0]["name"] = output_filename

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            print(f"Processed: {input_path} -> {output_path}")
            print(f"Updated table '{original_tables[0]['table_name']}' file_path and name to: data/{output_filename}")
            if headers != new_headers:
                print("Headers modified:")
                for old, new in zip(headers, new_headers):
                    if old != new:
                        print(f"  '{old}' -> '{new}'")
    print("\nYou can now run your connector with: python -m my-connector-package")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <input_file>")
        print("\nThis script will:")
        print("  1. Preprocess the file (normalize headers)")
        print("  2. Copy it to the data/ directory as CSV with a timestamped name")
        print("  3. Update __config.json to use the new file")
        print("\nSupported formats: CSV, Excel (.xlsx, .xls, .xlsm, .xlsb), ZIP (containing CSVs)")
        sys.exit(1)
    process_new_input_file(sys.argv[1])
