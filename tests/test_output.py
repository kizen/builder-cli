"""Unit tests for the unified output layer (kizen_builder.output)."""

from __future__ import annotations

import csv
import io

import pytest
import typer

from kizen_builder import output as out

# --- resolve_format ---------------------------------------------------------


def test_resolve_format_defaults_to_table():
    assert out.resolve_format(None, False) is out.OutputFormat.TABLE


def test_resolve_format_json_flag_wins():
    # The legacy --json alias overrides --output for back-compat.
    assert out.resolve_format(None, True) is out.OutputFormat.JSON
    assert out.resolve_format("csv", True) is out.OutputFormat.JSON


@pytest.mark.parametrize(
    "value,expected",
    [
        ("json", out.OutputFormat.JSON),
        ("CSV", out.OutputFormat.CSV),
        ("Table", out.OutputFormat.TABLE),
    ],
)
def test_resolve_format_case_insensitive(value, expected):
    assert out.resolve_format(value, False) is expected


def test_resolve_format_bad_value_raises_bad_parameter():
    with pytest.raises(typer.BadParameter):
        out.resolve_format("yaml", False)


# --- cell_str flattening ----------------------------------------------------


def test_cell_str_none_is_empty():
    assert out.cell_str(None) == ""


def test_cell_str_money_dict_uses_amount():
    assert (
        out.cell_str({"currency": "USD", "symbol": "$", "amount": 320.81}) == "320.81"
    )


def test_cell_str_named_dict_uses_name():
    assert out.cell_str({"id": "x", "name": "Widget"}) == "Widget"


def test_cell_str_opaque_dict_falls_back_to_compact_json():
    # A relationship dict with no display-ish key → compact JSON, no spaces.
    got = out.cell_str({"id": "x", "first_name": "Alex"})
    assert got == '{"id":"x","first_name":"Alex"}'


def test_cell_str_list_joins_items():
    assert out.cell_str(["a", "b", "c"]) == "a; b; c"
    assert out.cell_str([{"name": "one"}, {"name": "two"}]) == "one; two"


def test_cell_str_bool_lowercase():
    assert out.cell_str(True) == "true"
    assert out.cell_str(False) == "false"


# --- record_csv_columns -----------------------------------------------------


def _record(rec_id, fields):
    return {
        "id": rec_id,
        "fields": {
            f"uuid-{i}": {"id": f"uuid-{i}", "name": name, "value": value}
            for i, (name, value) in enumerate(fields.items())
        },
    }


def test_record_csv_columns_id_first_then_union_in_first_seen_order():
    records = [
        _record("r1", {"ticker": "VTI", "shares": 5}),
        _record("r2", {"ticker": "BND", "note": "x"}),  # adds `note`
    ]
    cols = out.record_csv_columns(records)
    assert [c.header for c in cols] == ["id", "ticker", "shares", "note"]


def test_record_csv_columns_ragged_records_line_up():
    # r2 is missing `shares` → its cell is empty, not a shifted column.
    records = [
        _record("r1", {"ticker": "VTI", "shares": 5}),
        _record("r2", {"ticker": "BND"}),
    ]
    cols = out.record_csv_columns(records)
    rows = list(csv.reader(io.StringIO(out._write_csv(records, cols))))
    assert rows[0] == ["id", "ticker", "shares"]
    assert rows[1] == ["r1", "VTI", "5"]
    assert rows[2] == ["r2", "BND", ""]  # shares empty, columns aligned


def test_emit_csv_always_writes_header_for_empty_rows(capsys):
    cols = [out.Column("id", "id"), out.Column("name", "name")]
    out.emit_csv([], cols)
    assert capsys.readouterr().out.strip() == "id,name"
