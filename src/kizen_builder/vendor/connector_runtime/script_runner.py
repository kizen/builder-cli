import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from enum import Enum

import logging
import time
import os
import re
import sys

import json
from functools import cached_property

from charset_normalizer import detect
from python_calamine import load_workbook


def _get_chdb():
    import chdb

    return chdb


class SplitStreamHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.stdout_handler = logging.StreamHandler(sys.stdout)
        self.stderr_handler = logging.StreamHandler(sys.stderr)

        # Use the same formatter for both handlers
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.stdout_handler.setFormatter(formatter)
        self.stderr_handler.setFormatter(formatter)

    def emit(self, record):
        if record.levelno <= logging.INFO:
            self.stdout_handler.emit(record)
        else:
            self.stderr_handler.emit(record)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(SplitStreamHandler())
logger.propagate = False


class SQLRunnerException(Exception):
    pass


class SQLSecurityException(SQLRunnerException):
    pass


@dataclass
class InputMetadataTable:
    table_name: str
    name: str
    columns_mapping: list


NAMED_NULLABLE_RELATIONSHIP_TUPLE = "Tuple(id Nullable(UUID), name Nullable(String))"
NULLABLE_RELATIONSHIP_TUPLE = "Tuple(Nullable(UUID),Nullable(String))"

META_CURRENT_EXECUTION_COLUMNS = [
    {"col": "business_id", "type": "str"},
    {"col": "connector_id", "type": "str"},
    {"col": "execution_id", "type": "str"},
    {"col": "trigger_type", "type": "str"},
    {"col": "triggered_by_id", "type": "str"},
    {"col": "triggered_by_desc", "type": "str"},
    {"col": "trigger_auth", "type": "str"},
    {"col": "fileupload_file_size_bytes", "type": "int"},
    {"col": "fileupload_file_name", "type": "str"},
    {"col": "fileupload_file_id", "type": "str"},
    {"col": "is_dry_run", "type": "bool"},
    {"col": "cadence", "type": "str"},
    {"col": "timeframe_start", "type": "int"},
    {"col": "bulkaction_fields", "type": "str"},
    {"col": "entity_records_set_key", "type": "str"},
    {"col": "activity_object_id", "type": "str"},
]

CLICKHOUSE_MAX_MEMORY = int(os.getenv("CLICKHOUSE_MAX_MEMORY", 10000000000))
CLICKHOUSE_MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY = int(
    os.getenv("CLICKHOUSE_MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY", 4000000000)
)  # 8GB
CLICKHOUSE_MAX_BYTES_BEFORE_EXTERNAL_SORT = int(
    os.getenv("CLICKHOUSE_MAX_BYTES_BEFORE_EXTERNAL_SORT", 4000000000)
)  # 2GB
CLICKHOUSE_MAX_EXECUTION_TIME = int(os.getenv("CLICKHOUSE_MAX_EXECUTION_TIME", 300))  # 5 minutes
CLICKHOUSE_MAX_THREADS = int(os.getenv("CLICKHOUSE_MAX_THREADS", 4))  # 4 threads max
MAX_ERROR_MESSAGE_LENGTH = int(os.getenv("MAX_ERROR_MESSAGE_LENGTH", 5000))  # Maximum error message length
# Threshold for when to start truncating (default 50KB)
ERROR_TRUNCATION_THRESHOLD = int(os.getenv("ERROR_TRUNCATION_THRESHOLD", 50000))


def truncate_error_message(error_message: str, max_length: int = MAX_ERROR_MESSAGE_LENGTH) -> str:
    """
    Truncate error messages that are too long, removing null bytes and other non-printable characters.

    For messages under ERROR_TRUNCATION_THRESHOLD, no truncation is performed.
    For longer messages, keeps the beginning and end, removing the middle portion.
    """
    if not error_message:
        return error_message

    clean_message = "".join(char for char in error_message if ord(char) >= 32 or char in "\n\t")

    # Don't truncate if under the threshold (default 50KB)
    if len(clean_message) <= ERROR_TRUNCATION_THRESHOLD:
        return clean_message

    if len(clean_message) <= max_length:
        return clean_message
    keep_size = min(24576, (max_length - 100) // 2)

    beginning = clean_message[:keep_size]
    ending = clean_message[-keep_size:]

    omitted_count = len(clean_message) - (2 * keep_size)

    return f"{beginning}\n\n...[Error message truncated - {omitted_count} characters omitted here]...\n\n{ending}"


class ChDBScriptRunner:
    """
    Class to run SQL script using ChDB session and generate output files
    """

    class DBNames(Enum):
        INPUT = "input"
        OUTPUT = "output"
        CONNECTOR = "connector"
        KIZEN = "kizen"
        META = "meta"

    TYPE_MAPPING = {
        "int": "Nullable(Int64)",
        "str": "Nullable(String)",
        "float": "Nullable(Float64)",
        "bool": "Nullable(UInt8)",
        "date": "Nullable(Date32)",
        "datetime": "Nullable(DateTime64(9))",
        "array[tuple[uuid,string]]": f"Array({NULLABLE_RELATIONSHIP_TUPLE})",
        "tuple[uuid,string]": NAMED_NULLABLE_RELATIONSHIP_TUPLE,
        "array[string]": "Array(String)",
        "array[uuid]": "Array(UUID)",
        "uuid": "Nullable(UUID)",
        "json": "JSON",
    }

    FILE_TYPE_MAPPING = {
        "date": "Nullable(String)",
        "datetime": "Nullable(String)",
        "int": "Nullable(String)",
        "float": "Nullable(String)",
        "array[string]": "String",
        "array[uuid]": "String",
        "tuple[uuid,string]": "String",
        "array[tuple[uuid,string]]": "String",
    }

    # Use parse function or None to properly catch errors (overflow, invalid data, etc.)
    SELECT_EXPRESSION = {
        "datetime": lambda x: f"IF({x} IS NOT NULL AND {x} != '', parseDateTime64BestEffortOrNull({x}, 9), NULL) AS {x}",
        "array[string]": lambda x: f"splitByChar(',', {x}) as {x}",
        "array[uuid]": lambda x: f"IF({x} IS NOT NULL AND {x} != '' AND {x} != '[]', JSONExtract({x}, 'Array(UUID)'), []) as {x}",
        "tuple[uuid,string]": lambda x: f"arrayElement(JSONExtract({x}, 'Array({NAMED_NULLABLE_RELATIONSHIP_TUPLE})'), 1) as {x}",
        "array[tuple[uuid,string]]": lambda x: f"JSONExtract({x}, 'Array({NULLABLE_RELATIONSHIP_TUPLE})') as {x}",
    }

    def __init__(
        self,
        config: dict,
        user_script: str,
        config_file_path: str,
        data_dir: str = "data",
        dry_run=False,
        output_dir: str = None,
        integration_secrets: list = None,
    ):
        self.config_file_path = config_file_path
        self.config = config
        self.user_script = user_script
        self.data_dir = data_dir
        self.integration_secrets = integration_secrets
        self.init_script = (
            "--This script is auto-generated to setup the databases and tables\n"
            "--extracted from the reference file of the connector\n\n"
        )
        self._apply_session_resource_limits(dry_run)
        self._init_named_collections(dry_run)
        self._init_db(dry_run)
        self._init_tables(dry_run)
        self.output_dir = output_dir

    @cached_property
    def session(self):
        chdb = _get_chdb()
        current_version = chdb.__version__
        version_tuple = tuple(map(int, current_version.split(".")))

        if version_tuple == (1, 3, 1):
            from chdb.session import Session

            session = Session()
        else:
            session = chdb.session.Session()

        if version_tuple >= (3, 1, 0):
            session.query("SET allow_experimental_json_type=1;")
        return session

    def _init_db(self, dry_run=False):
        for db_name in self.DBNames:
            script = f"CREATE DATABASE IF NOT EXISTS {db_name.value};\n\n"
            if not dry_run:
                self.session.query(script)
            self.init_script += script

    def _apply_session_resource_limits(self, dry_run: bool) -> None:
        """Apply resource limits to the ChDB session that will affect all queries."""

        if dry_run:
            return

        self.session.query(f"""
            SET max_memory_usage = {CLICKHOUSE_MAX_MEMORY};
            SET max_bytes_before_external_group_by = {CLICKHOUSE_MAX_BYTES_BEFORE_EXTERNAL_GROUP_BY};
            SET max_bytes_before_external_sort = {CLICKHOUSE_MAX_BYTES_BEFORE_EXTERNAL_SORT};
            SET max_execution_time = {CLICKHOUSE_MAX_EXECUTION_TIME};
            SET max_threads = {CLICKHOUSE_MAX_THREADS};
        """)

        logger.info(
            {
                "log_event": "sql_runner_resource_limits",
                "message": "Applied resource limits to ChDB session",
                "limits": {
                    "max_memory_usage": f"{CLICKHOUSE_MAX_MEMORY}",
                    "max_execution_time": f"{CLICKHOUSE_MAX_EXECUTION_TIME}",
                    "max_threads": f"{CLICKHOUSE_MAX_THREADS}",
                },
            }
        )

    @classmethod
    def get_col_type(cls, col_type: str):
        return cls.TYPE_MAPPING.get(col_type, "Nullable(String)")

    @classmethod
    def get_file_col_type(cls, col_type: str):
        return cls.FILE_TYPE_MAPPING.get(col_type) or cls.get_col_type(col_type)

    def _init_named_collections(self, dry_run):
        if (
            not self.config.get("integration_secret_filenames") or self.config.get("integration_secret_filenames") == []
        ) and not self.integration_secrets:
            return

        def _create_named_collection(integration_secret_name, secret_json):
            collection_name = integration_secret_name.split(".")[0]
            if not secret_json:
                return

            # Always create placeholder script for init_script (dev package security)
            placeholder_pairs = []
            kv_pairs = []
            for k, v in secret_json.items():
                placeholder_value = f"enter_{k}_here"
                placeholder_pairs.append(f"  {k} = '{placeholder_value}'")
                safe_v = str(v).replace("'", "''")
                kv_pairs.append(f"  {k} = '{safe_v}'")
            placeholder_kv_pairs_str = ",\n".join(placeholder_pairs)
            self.init_script += f"DROP NAMED COLLECTION IF EXISTS {collection_name};\nCREATE NAMED COLLECTION {collection_name} AS\n{placeholder_kv_pairs_str};\n\n"
            kv_pairs_str = ",\n".join(kv_pairs)
            runtime_script = f"CREATE NAMED COLLECTION {collection_name} AS\n{kv_pairs_str};\n\n"
            if not dry_run:
                self.session.query(runtime_script)

            # delete secret file if exists
            secret_file_path = os.path.join(self.data_dir, f"{integration_secret_name}")
            if self.data_dir != "data" and os.path.exists(secret_file_path):
                os.remove(secret_file_path)

        if self.integration_secrets:
            for secret in self.integration_secrets:
                _create_named_collection(secret.api_name, json.loads(secret.value))
        else:
            for integration_secret in self.config.get("integration_secret_filenames"):
                secret_file_path = os.path.join(self.data_dir, f"{integration_secret}")
                if os.path.exists(secret_file_path):
                    with open(secret_file_path, "r") as f:
                        secret_json = json.load(f)
                    _create_named_collection(integration_secret, secret_json)

    def _init_tables(self, dry_run):
        def _create_input_table(namespace, page, page_idx=None):
            table_columns = ", ".join(
                f"{clean_sql_name(val['col'])} {self.get_col_type(val['type'])}"
                for val in page.get("columns_mapping", [])
            )
            file_columns = ", ".join(
                f"{clean_sql_name(val['col'])} {self.get_file_col_type(val['type'])}"
                for val in page.get("columns_mapping", [])
            )
            selected_fields = ", ".join(
                [
                    self.SELECT_EXPRESSION.get(v["type"], lambda value: value)(clean_sql_name(v["col"]))
                    for v in page.get("columns_mapping", [])
                ]
            )

            if namespace == self.DBNames.META.value:
                file_format = "JSONEachRow"
            else:
                file_format = "CSVWithNames"

            escaped_file_name = page.get("name", "").replace("'", "''")
            table_type = f"CREATE VIEW {namespace}.{if_table_name_not_clean_sql_name_quote(page.get('table_name'))}\n \t({table_columns})\n AS\n SELECT {selected_fields}\n"
            if page.get("table_name") == "webhooks":
                table_type = f"CREATE VIEW {namespace}.{page.get('table_name')} as\n SELECT fromUnixTimestamp64Milli(toInt64(timestamp)) as timestamp, employee_id, querystring, body \n"
            elif page.get("table_name") == "schedule":
                table_type = f"CREATE VIEW {namespace}.{page.get('table_name')} as\n SELECT parseDateTimeBestEffort(schedule_trigger_time) as schedule_trigger_time \n"
            script = (
                table_type + f"FROM file('{self.data_dir}/{escaped_file_name}', '{file_format}', '{file_columns}')\n"
                f"SETTINGS format_csv_null_representation = '', input_format_csv_allow_variable_number_of_columns=1;\n\n\n"
            )

            if page_idx is not None:
                script += f"""CREATE VIEW {namespace}.page_idx_{page_idx} AS SELECT * FROM {namespace}.{if_table_name_not_clean_sql_name_quote(page.get('table_name'))};\n\n\n"""

            if not dry_run:
                self.session.query(script)
            self.init_script += script

        self.input_metadata_records = []
        for page in self.config.get("input_tables", []):
            _create_input_table(self.DBNames.INPUT.value, page, page["page_idx"])
            escaped_name = page.get("name", "").replace("'", "''")
            if self.data_dir:
                self.input_metadata_records.append(
                    f"('{self.DBNames.INPUT.value}', '{page.get('table_name')}', '{self.data_dir}/{escaped_name}')"
                )
            else:
                self.input_metadata_records.append(
                    f"('{self.DBNames.INPUT.value}', '{page.get('table_name')}', '{escaped_name}')"
                )

        for seed in self.config.get("seed_tables", []):
            seed["table_name"] = if_table_name_not_clean_sql_name_quote(seed["table_name"])
            seed["name"] = filename_clean_sql_name_if_special_characters(seed["name"])
            _create_input_table(self.DBNames.KIZEN.value, seed)

        if self.config_file_path:
            meta = InputMetadataTable(
                table_name="current_execution",
                name=os.path.basename(self.config_file_path),
                columns_mapping=META_CURRENT_EXECUTION_COLUMNS,
            )

            _create_input_table(self.DBNames.META.value, asdict(meta))

        if not os.path.exists(self.data_dir):
            from io import StringIO

            inputs_csv_buffer = StringIO()
            inputs_writer = csv.writer(inputs_csv_buffer)
            inputs_writer.writerow(["database", "table", "file_path"])

            for record in self.input_metadata_records:
                values = record.strip("()").split(",")
                values = [v.strip().strip("'") for v in values]
                inputs_writer.writerow(values)

            params_csv_buffer = StringIO()
            params_writer = csv.writer(params_csv_buffer)
            params_writer.writerow(["name", "value"])

            if self.config.get("sql_parameters"):
                for k, v in self.config.get("sql_parameters", {}).items():
                    params_writer.writerow([k, str(v)])

            inputs_csv_content = inputs_csv_buffer.getvalue().replace("'", "''")
            params_csv_content = params_csv_buffer.getvalue().replace("'", "''")

            meta_inputs_script = f"""
            CREATE DATABASE IF NOT EXISTS meta;

            -- Drop existing tables if they exist
            DROP TABLE IF EXISTS meta.inputs;
            DROP TABLE IF EXISTS meta.parameters;

            -- Create inputs table from CSV
            CREATE TABLE meta.inputs
            (
                database String,
                table String,
                file_path String
            )
            ENGINE = Log;

            -- Create parameters table from CSV
            CREATE TABLE meta.parameters
            (
                name String,
                value String
            )
            ENGINE = Log;

            -- Insert data directly from CSV content
            INSERT INTO meta.inputs SELECT * FROM format(CSV, 'database String, table String, file_path String', '{inputs_csv_content}');
            {"INSERT INTO meta.parameters SELECT * FROM format(CSV, 'name String, value String', '" + params_csv_content + "');" if self.config.get("sql_parameters") else ""}
            """
        else:
            # Use file-based approach when data_dir exists
            inputs_csv_path = os.path.join(self.data_dir, "inputs.csv")
            params_csv_path = os.path.join(self.data_dir, "parameters.csv")

            with open(inputs_csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["database", "table", "file_path"])

                for record in self.input_metadata_records:
                    values = record.strip("()").split(",")
                    values = [v.strip().strip("'") for v in values]
                    writer.writerow(values)

            with open(params_csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["name", "value"])

                for k, v in self.config.get("sql_parameters", {}).items():
                    writer.writerow([k, str(v)])

            meta_inputs_script = f"""
            CREATE DATABASE IF NOT EXISTS meta;

            -- Drop existing tables if they exist
            DROP TABLE IF EXISTS meta.inputs;
            DROP TABLE IF EXISTS meta.parameters;

            -- Create inputs table from CSV
            CREATE TABLE meta.inputs
            (
                database String,
                table String,
                file_path String
            )
            ENGINE = Log;

            -- Create parameters table from CSV
            CREATE TABLE meta.parameters
            (
                name String,
                value String
            )
            ENGINE = Log;

            -- Insert data from CSV files
            INSERT INTO meta.inputs SELECT * FROM file('{inputs_csv_path}', 'CSVWithNames');
            {"INSERT INTO meta.parameters SELECT * FROM file('" + params_csv_path + "', 'CSVWithNames');" if self.config.get("sql_parameters") else ""}
            """

        if not dry_run:
            self.session.query(meta_inputs_script)

        self.init_script += meta_inputs_script

    def _get_output_tables(self) -> list[str]:
        res = self.session.query("""
            SELECT DISTINCT name from system.tables WHERE database = 'output' order by name;
        """)

        if not res:
            raise SQLRunnerException(
                "No output tables found in output database, please ensure your SQL script generates output tables in "
                "the output database."
            )

        return [r[1:-1] for r in res.data().split()]

    def _save_output_tables(self, start_time: float, raise_if_no_tables: bool = True) -> dict:
        """
        Save output tables to CSV files and return metadata.

        Args:
            start_time: The start time of the execution
            raise_if_no_tables: If True, raise an exception if no output tables are found

        Returns:
            Dictionary containing output files metadata and statistics
        """
        output_files = []
        total_num_rows = 0
        total_num_columns = 0
        stats_per_scope = {}

        output_directory = os.path.join(self.data_dir, "output")
        os.makedirs(output_directory, exist_ok=True)

        try:
            output_tables = self._get_output_tables()
        except SQLRunnerException:
            if raise_if_no_tables:
                raise
            return {
                "output_files": [],
                "time_to_process": round(time.time() - start_time, 2),
                "stats_per_scope": {},
                "stats": {
                    "num_columns": 0,
                    "num_rows": 0,
                    "num_output_tables": 0,
                },
                "partial_output": True,
            }

        for table in output_tables:
            file_path = f"{output_directory}/{table}.csv"
            try:
                stats = self.session.query(f"""WITH
                    (SELECT count(*) FROM system.columns WHERE database = '{self.DBNames.OUTPUT.value}' AND table = '{table}') AS num_columns,
                    (SELECT count(*) FROM {self.DBNames.OUTPUT.value}.{table}) AS num_rows
                SELECT
                    num_columns,
                    num_rows;
                """)

                stats = stats.data().strip().split(",")
                num_rows = int(stats[1])
                num_columns = int(stats[0])
                stats_per_scope[table] = {"num_rows": num_rows, "num_columns": num_columns}

                total_num_rows += num_rows
                total_num_columns += num_columns

                self.session.query(
                    f"""INSERT INTO FUNCTION file('{file_path}', 'CSVWithNames')
                    SELECT * FROM {self.DBNames.OUTPUT.value}.{table}
                    settings engine_file_truncate_on_insert = 1;"""
                )

                output_files.append(
                    {
                        "file_path": f"{self.output_dir if self.output_dir else output_directory}/{table}.csv",
                        "size": os.path.getsize(file_path),
                        "file_name": f"{table}.csv",
                    }
                )
            except Exception as table_error:
                logger.warning(
                    {
                        "log_event": "partial_output_table_error",
                        "message": f"Failed to export table {table}",
                        "table": table,
                        "error": str(table_error),
                    }
                )

        return {
            "output_files": output_files,
            "time_to_process": round(time.time() - start_time, 2),
            "stats_per_scope": stats_per_scope,
            "stats": {
                "num_columns": total_num_columns,
                "num_rows": total_num_rows,
                "num_output_tables": len(output_files),
            },
        }

    def run(self) -> dict:
        logger.info({"log_event": "sql_runner", "message": "Start running SQL script"})
        start_time = time.time()

        self.session.query("USE connector;")

        sql_execution_error = None
        partial_output_metadata = None

        try:
            self.session.query(self.user_script)
        except Exception as e:
            # Do a simple select for CHDB 3.4 swallowing first query after error issue
            self.session.query("select 1;")
            sql_execution_error = e
            truncated_error = truncate_error_message(str(e))

            logger.info({"log_event": "sql_runner", "message": "SQL script failed, attempting to save partial outputs"})
            try:
                partial_output_metadata = self._save_output_tables(start_time, raise_if_no_tables=False)

                if partial_output_metadata and partial_output_metadata.get("output_files"):
                    logger.info(
                        {
                            "log_event": "partial_output_saved",
                            "message": f"Saved {len(partial_output_metadata['output_files'])} partial output files",
                            "num_files": len(partial_output_metadata.get("output_files", [])),
                        }
                    )
                    partial_output_metadata["partial_output"] = True
                    partial_output_metadata["error"] = truncated_error
            except Exception as save_error:
                logger.warning(
                    {
                        "log_event": "partial_output_save_failed",
                        "message": "Failed to save partial outputs",
                        "error": str(save_error),
                    }
                )

            if "Memory limit" in truncated_error:
                error_msg = (
                    "Memory limit exceeded. Please optimize your query by filtering data, "
                    "using more efficient joins, or simplifying complex operations."
                )
            elif "Timeout exceeded" in truncated_error:
                error_msg = (
                    "Query execution time limit exceeded (5 minutes). Consider adding appropriate filters, "
                    "optimizing joins, or breaking the query into smaller parts."
                )
            elif "Limit for" in truncated_error and "rows" in truncated_error:
                error_msg = (
                    "Row limit exceeded (10M rows). Add filters to process fewer rows or "
                    "consider processing your data in smaller batches."
                )
            else:
                error_msg = f"Error running connector SQL script: {truncated_error}"

            if partial_output_metadata and partial_output_metadata.get("output_files"):
                self.partial_output_metadata = partial_output_metadata

            raise SQLRunnerException(error_msg) from sql_execution_error

        result_metadata = self._save_output_tables(start_time, raise_if_no_tables=True)

        logger.info({"log_event": "sql_runner", "message": "SQL script ran successfully"} | result_metadata)
        return result_metadata


CHDB_RESTRICTED_CHAR_REGEX = re.compile(r"[^a-zA-Z0-9_]")


def clean_sql_name(col_name, check_starting_digit=True, lower_case=True):
    if not col_name:
        return col_name
    col_name = str(col_name)
    sql_name = CHDB_RESTRICTED_CHAR_REGEX.sub("_", col_name.strip())
    if lower_case:
        sql_name = sql_name.lower()
    if check_starting_digit and sql_name and sql_name[0].isdigit():
        # CHDB SQL doesn't support column names starting with digits
        sql_name = f"_{sql_name}"
    return sql_name


def detect_encoding_from_buffer(sample_data):
    try:
        sample_data.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        logger.warning("Failed to decode buffer sample as UTF-8, attempting encoding detection")
        result = detect(sample_data)
        detected_encoding = result["encoding"]
        if not detected_encoding:
            logger.warning("No encoding detected, falling back to utf-8 with error replacement")
            detected_encoding = "utf-8"

    logger.info(f"Detected encoding: {detected_encoding}")
    return detected_encoding


def dedupe_and_normalize_headers(headers):
    columns = defaultdict(int)
    result = []
    empty_counter = 1
    for header in headers:
        header = clean_sql_name(header)
        if not header:
            header = f"_{empty_counter}"
            empty_counter += 1
            result.append(header)
            continue
        count = columns[header]
        if count > 0:
            formatted_header = f"{header}__duplicate_{count}__"
            if formatted_header in headers:
                raise ValueError(
                    f"Generating duplicate header format conflict: generated duplicate header - '{formatted_header}' already exists in headers"
                )
            result.append(formatted_header)
        else:
            result.append(header)
        columns[header] += 1
    return result


def process_excel_sheet_to_csv(sheet, output_path, row_callback=None):
    headers = []
    new_headers = []

    with open(output_path, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

        if sheet.total_height == 0 and sheet.total_width == 0:
            writer.writerow(["_1"])
            return ["_1"], ["_1"]

        for row_idx, row in enumerate(sheet.to_python(skip_empty_area=False)):
            row_data = list(row)
            if row_idx == 0:
                headers = row_data
                new_headers = dedupe_and_normalize_headers(headers)
                writer.writerow(new_headers)
            else:
                if row_callback:
                    row_data = row_callback(row_data, row_idx)
                writer.writerow(row_data)

    return headers, new_headers


def process_excel_to_csv(input_path, output_path):
    workbook = load_workbook(input_path)
    if not workbook.sheet_names:
        raise ValueError("Excel file has no sheets")

    sheet = workbook.get_sheet_by_name(workbook.sheet_names[0])
    return process_excel_sheet_to_csv(sheet, output_path)


def process_excel_to_csvs(input_path: str, output_dir: str) -> list[dict]:
    """
    Process an Excel file with multiple sheets, extracting each sheet to a separate CSV.

    Returns a list of dicts with keys: file_name, table_name, headers, new_headers, output_path
    """
    workbook = load_workbook(input_path)
    if not workbook.sheet_names:
        raise ValueError("Excel file has no sheets")

    results = []
    seen_tablenames = set()
    seen_filenames = defaultdict(int)

    for idx, sheet_name in enumerate(workbook.sheet_names):
        sheet = workbook.get_sheet_by_name(sheet_name)
        table_name = clean_sql_name(sheet_name, check_starting_digit=False)

        if table_name in seen_tablenames:
            count = seen_filenames[table_name]
            seen_filenames[table_name] += 1
            formatted_table_name = f"{table_name}__duplicate_{count}__"
            if formatted_table_name in seen_tablenames:
                raise ValueError(f"Generating duplicate sheet name conflict: '{formatted_table_name}' already exists")
            table_name = formatted_table_name
        else:
            seen_tablenames.add(table_name)
            seen_filenames[table_name] += 1

        output_filename = f"{table_name}.csv"
        output_path = os.path.join(output_dir, output_filename)

        headers, new_headers = process_excel_sheet_to_csv(sheet, output_path)

        results.append(
            {
                "file_name": output_filename,
                "table_name": table_name,
                "headers": headers,
                "new_headers": new_headers,
                "output_path": output_path,
            }
        )

    return results


def process_zip_to_csvs(input_path: str, output_dir: str) -> list[dict]:
    """
    Process a ZIP file containing CSVs, extracting and normalizing headers for each.

    Returns a list of dicts with keys: file_name, table_name, headers, new_headers, output_path
    """
    zip_name = os.path.splitext(os.path.basename(input_path))[0]
    results = []
    seen_tablenames = set()
    seen_filenames = defaultdict(int)

    with zipfile.ZipFile(input_path, "r") as zipf:
        csv_files = [
            zipinfo
            for zipinfo in zipf.infolist()
            if (
                zipinfo.filename.lower().endswith(".csv")
                and (os.path.dirname(zipinfo.filename) == "" or os.path.dirname(zipinfo.filename) == zip_name)
                and not zipinfo.filename.startswith("__MACOSX/")
                and not os.path.basename(zipinfo.filename).startswith("._")
            )
        ]

        if not csv_files:
            raise ValueError("ZIP file contains no valid CSV files at root level")

        for zipinfo in csv_files:
            file_basename = os.path.basename(zipinfo.filename)
            name_without_extension = os.path.splitext(file_basename)[0]
            table_name = clean_sql_name(name_without_extension, check_starting_digit=False)

            if table_name in seen_tablenames:
                count = seen_filenames[table_name]
                seen_filenames[table_name] += 1
                formatted_table_name = f"{table_name}__duplicate_{count}__"
                if formatted_table_name in seen_tablenames:
                    raise ValueError(f"Generating duplicate filename conflict: '{formatted_table_name}' already exists")
                table_name = formatted_table_name
            else:
                seen_tablenames.add(table_name)
                seen_filenames[table_name] += 1

            output_filename = f"{table_name}.csv"
            output_path = os.path.join(output_dir, output_filename)

            with zipf.open(zipinfo) as csv_file:
                content = csv_file.read()
                sample_data = content[:65536]
                encoding = detect_encoding_from_buffer(sample_data)

                text_content = content.decode(encoding, errors="replace")
                lines = text_content.split("\n")
                if not lines:
                    continue

                reader = csv.reader(io.StringIO(lines[0] + "\n"))
                headers = next(reader, [])
                new_headers = dedupe_and_normalize_headers(headers)

                with open(output_path, "w", encoding="utf-8", newline="") as outfile:
                    writer = csv.writer(outfile, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
                    writer.writerow(new_headers)

                    if len(lines) > 1:
                        remaining_content = "\n".join(lines[1:])
                        remaining_reader = csv.reader(io.StringIO(remaining_content))
                        for row in remaining_reader:
                            if row:
                                writer.writerow(row)

            results.append(
                {
                    "file_name": output_filename,
                    "table_name": table_name,
                    "headers": headers,
                    "new_headers": new_headers,
                    "output_path": output_path,
                }
            )

    return results


def if_table_name_not_clean_sql_name_quote(table_name):
    """
    Return a quoted column name if it doesn't match valid SQL identifier pattern.
    Escapes unescaped double and single quotes with backslashes.
    Also removes asterisks (*) from the name.

    Args:
        table_name (str): table_name to check

    Returns:
        str: Original name if valid SQL identifier, otherwise quoted name with proper escaping
    """
    if not table_name:
        return table_name

    # Remove any asterisks (*) from the table name
    table_name = str(table_name).replace("*", "")

    valid_sql_identifier_pattern = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

    if valid_sql_identifier_pattern.match(str(table_name)):
        return table_name

    if len(table_name) >= 2 and table_name.startswith('"') and table_name.endswith('"'):
        table_name = table_name[1:-1]

    escaped_name = ""
    i = 0
    while i < len(table_name):
        char = table_name[i]

        if (char == '"' or char == "'") and (i == 0 or table_name[i - 1] != "\\"):
            escaped_name += "\\" + char
        else:
            escaped_name += char

        i += 1

    return f'"{escaped_name}"'


def filename_clean_sql_name_if_special_characters(table_name: str) -> str:
    """
    Return a normalized table name if it doesn't match valid SQL identifier pattern.
    """
    if not table_name:
        return table_name
    base_name, ext = os.path.splitext(table_name)
    valid_sql_identifier_pattern = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

    if valid_sql_identifier_pattern.match(str(base_name)):
        return table_name
    else:
        hash_value = 0
        for char in str(table_name):
            hash_value = (hash_value * 31 + ord(char)) & 0xFFFFFFFF
        name_hash = format(hash_value % 60466176, "05x")
        clean_name = clean_sql_name(f"{base_name}")
        if ext:
            return f"{clean_name}_{name_hash}{ext}"
        else:
            return f"{clean_name}_{name_hash}"
