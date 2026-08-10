"""
UI ↔ DSL filter parity tests.

Every test in this module encodes a filter payload that was captured from the
v2 staging UI by building the filter manually and recording the JSON POSTed to
/api/records/<obj_id>/search (see docs/ui_filter_capture.md for the full
capture log and condition-token tables).

The assertions are the spec: the python DSL must be able to generate each of
these payloads. Tests that fail indicate missing/incorrect DSL behavior to be
implemented in kizen/filtering.py (intentionally left as plain failing tests
for handoff).

All field/option uuids below are from the "Policies" object on staging
(business "Aalii"), same fixture environment as conftest.py.
"""

from datetime import UTC, date, datetime

import pytest

from kizen_builder.filtering import All, Any, Field, Options, filter_context

# --- Policies object field uuids (staging) ---------------------------------
FTEXT = "921cec5c-9f68-4cd1-bf30-b11f00571175"
FEMAIL = "11c84d9f-1a28-467f-9260-6cb013d04846"
FLONGTEXT = "2072621b-9dd3-4c54-aa0a-d35b8e829b9a"
FPHONENUMBER = "493c11cf-a357-4afa-b356-3c8d082832b3"
FCHECKBOX = "fdaadc16-bc4b-4cc0-bee0-609b84c12293"
FCHECKBOXES = "88171c43-d47b-4706-aa10-4bf2f1b4d4ef"
FDYNAMICTAGS = "d9d3a405-42cb-4158-b15d-073ab2270893"
FDROPDOWN = "cc3c8cac-d614-4850-b38d-55e9c8ba7ed4"
FRADIOBUTTONS = "186eb6e8-197f-44ed-a2c2-b67a8ea5a096"
FSTATUS = "0f5900a4-a799-4108-9010-12b3ba577d77"
FYESNOMAYBE = "2f27f7a1-f957-4ff8-b16c-aa69fee899d9"
FRATING = "8f224ab8-b585-45f8-9b92-fc2fe1869aa2"
FINTEGER = "6a5c68f0-71e0-4308-b62e-67d114c0e69b"
FDECIMAL = "d88c9836-b82a-4862-b7d1-617b7c81629c"
FPRICE = "695ad3e6-5a12-45b1-ae4a-c11472f7edd8"
FDATE = "53a730c8-851b-4421-bbe7-cd4004ac052e"
FDATETIME = "3d574c03-a420-4175-b64d-5bbdc3f02822"
FFILES = "a70e1efc-f23e-4aaf-a39a-0b08f7814923"
FTEAMMEMBER = "0a40f245-a9bd-47df-bf1c-8a88583d29c5"
FRELATIONSHIP = "8cd45709-e199-4c7f-b193-d984e6bfe36a"  # primary_contact_record_0fe888

# Option uuids
DD1 = "82cd3986-8f04-4de3-acde-9c7f96aa73de"
DD2 = "c93df865-825e-41f2-a6e2-e9e5cdabed61"
DD3 = "1867428f-be13-48d1-b7c3-03647b83aeaf"
CB1 = "2a795c26-9478-4da8-bc22-5aba5497ea84"
CB2 = "e5c62880-fe99-43d1-ad20-5f3c93e28072"
CB3 = "df9c540d-d41c-450f-b94c-5b66a5d93e67"
DT1 = "5afe6e1c-8d1a-4e22-9be0-7bf08fd57cfd"
DT2 = "631ac69a-9718-4af7-b95f-3c561cf50a62"
RB1 = "ff6aaf15-3c7b-430d-afdf-bf23f26267ff"
RB2 = "82419070-4c69-4c5b-9181-e0442bfad14f"
S1 = "a3559536-7a1a-4ea6-b282-4c0f0bc2a37b"
YNM_YES = "f27f237d-f397-4a49-832d-83b2b79bc5f9"
YNM_MAYBE = "2c0de3ff-87f3-4510-9596-6ac832cfeaae"
STAGE_1 = "a82570ce-c4e4-4548-bbb7-8b77f94bbb9a"

# Employee uuid (a real team member on staging)
ALEC = "ca7e1a52-e930-45e9-a20d-e27eadbf020a"

# Contact record uuids used in relationship captures
CONTACT_A = "b5c0f6a1-133d-4519-b667-cfb88db4c7a6"
CONTACT_B = "34729d26-1a01-4839-9f52-894b63b93655"


def cf(field_uuid):
    """The "field" identifier the API expects for custom fields."""
    return f'"custom"::{field_uuid}'


def custom(field_uuid, condition, value, **extra):
    d = {
        "type": "fields_v2",
        "subtype": "custom",
        "field": cf(field_uuid),
        "condition": condition,
        "value": value,
    }
    d.update(extra)
    return d


def non_custom(field, condition, value, **extra):
    d = {
        "type": "fields",
        "subtype": "non_custom",
        "field": field,
        "condition": condition,
        "value": value,
    }
    d.update(extra)
    return d


def stage_filter(condition, value, **extra):
    d = {
        "type": "fields_v2",
        "subtype": "non_custom",
        "field": "stage",
        "overwrite": {"type": "stage"},
        "condition": condition,
        "value": value,
    }
    d.update(extra)
    return d


@pytest.fixture(autouse=True)
def policies_context(kizen):
    with filter_context("policies_policy"):
        yield


def filter_dicts(*conditions):
    """Render each FilterCondition to its API dict (no group wrapper)."""
    return [c.as_dict(parent=object()) for c in conditions]


# ---------------------------------------------------------------------------
# text / email
# ---------------------------------------------------------------------------


def test_text_field_all_conditions():
    assert filter_dicts(
        Field("ftext") == "abc",
        Field("ftext") != "abc",
        Field("ftext").contains("abc"),
        Field("ftext").not_contains("abc"),
        Field("ftext").startswith("abc"),
        Field("ftext").endswith("abc"),
        Field("ftext").not_startswith("abc"),
        Field("ftext").not_endswith("abc"),
        Field("ftext").is_blank(),
        Field("ftext").not_blank(),
    ) == [
        custom(FTEXT, "=", "abc"),
        custom(FTEXT, "!=", "abc"),
        custom(FTEXT, "contains", "abc"),
        custom(FTEXT, "!contains", "abc"),
        custom(FTEXT, "starts_with", "abc"),
        custom(FTEXT, "ends_with", "abc"),
        custom(FTEXT, "!starts_with", "abc"),
        custom(FTEXT, "!ends_with", "abc"),
        custom(FTEXT, "is_blank", True),
        custom(FTEXT, "is_blank", False),
    ]


def test_email_field_conditions():
    # email offers the same 10 conditions as text
    assert filter_dicts(
        Field("femail") == "a@b.com",
        Field("femail").not_contains("a@b.com"),
        Field("femail").not_blank(),
    ) == [
        custom(FEMAIL, "=", "a@b.com"),
        custom(FEMAIL, "!contains", "a@b.com"),
        custom(FEMAIL, "is_blank", False),
    ]


def test_longtext_field_conditions():
    # longtext only offers Is Blank / Isn't Blank in the UI
    assert filter_dicts(
        Field("flongtext").is_blank(),
        Field("flongtext").not_blank(),
    ) == [
        custom(FLONGTEXT, "is_blank", True),
        custom(FLONGTEXT, "is_blank", False),
    ]


def test_phonenumber_field_conditions():
    assert filter_dicts(
        Field("fphonenumber") == "555-1234",
        Field("fphonenumber").contains("555"),
        Field("fphonenumber").is_blank(),
        Field("fphonenumber").not_blank(),
    ) == [
        custom(FPHONENUMBER, "=", "555-1234"),
        custom(FPHONENUMBER, "contains", "555"),
        custom(FPHONENUMBER, "is_blank", True),
        custom(FPHONENUMBER, "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# checkbox / checkboxes / dynamictags
# ---------------------------------------------------------------------------


def test_checkbox_field_conditions():
    assert filter_dicts(
        Field("fcheckbox").is_checked(),
        Field("fcheckbox").not_checked(),
    ) == [
        custom(FCHECKBOX, "=", True),
        custom(FCHECKBOX, "=", False),
    ]


def test_checkboxes_field_conditions():
    assert filter_dicts(
        Field("fcheckboxes").contains("cb1"),
        Field("fcheckboxes").not_contains("cb2"),
        Field("fcheckboxes").is_any_of("cb1", "cb2"),
        Field("fcheckboxes").not_any_of("cb2", "cb3"),
        Field("fcheckboxes").is_blank(),
        Field("fcheckboxes").not_blank(),
    ) == [
        custom(FCHECKBOXES, "has", [CB1]),
        custom(FCHECKBOXES, "!has", [CB2]),
        custom(FCHECKBOXES, "has_any", [CB1, CB2]),
        custom(FCHECKBOXES, "!has_any", [CB2, CB3]),
        custom(FCHECKBOXES, "is_blank", True),
        custom(FCHECKBOXES, "is_blank", False),
    ]


def test_dynamictags_field_conditions():
    # dynamictags maps exactly like checkboxes in the UI
    # (UI labels: Has Value / Doesn't Have Value / Contains Any Of / Contains None Of)
    assert filter_dicts(
        Field("fdynamictags").contains("dt1"),
        Field("fdynamictags").not_contains("dt1"),
        Field("fdynamictags").is_any_of("dt1", "dt2"),
        Field("fdynamictags").not_any_of("dt1", "dt2"),
        Field("fdynamictags").is_blank(),
        Field("fdynamictags").not_blank(),
    ) == [
        custom(FDYNAMICTAGS, "has", [DT1]),
        custom(FDYNAMICTAGS, "!has", [DT1]),
        custom(FDYNAMICTAGS, "has_any", [DT1, DT2]),
        custom(FDYNAMICTAGS, "!has_any", [DT1, DT2]),
        custom(FDYNAMICTAGS, "is_blank", True),
        custom(FDYNAMICTAGS, "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# single-select option fields: dropdown / radio / status / yesnomaybe
# ---------------------------------------------------------------------------


def test_dropdown_field_conditions():
    # NOTE: the UI sends a BARE option uuid for = and !=, a list for any-of
    assert filter_dicts(
        Field("fdropdown") == "dd1",
        Field("fdropdown") != "dd1",
        Field("fdropdown").is_any_of("dd1", "dd2"),
        Field("fdropdown").not_any_of("dd2", "dd3"),
        Field("fdropdown").is_blank(),
        Field("fdropdown").not_blank(),
    ) == [
        custom(FDROPDOWN, "=", DD1),
        custom(FDROPDOWN, "!=", DD1),
        custom(FDROPDOWN, "is_any_of", [DD1, DD2]),
        custom(FDROPDOWN, "is_none_of", [DD2, DD3]),
        custom(FDROPDOWN, "is_blank", True),
        custom(FDROPDOWN, "is_blank", False),
    ]


def test_radiobuttons_field_conditions():
    assert filter_dicts(
        Field("fradiobuttons") == "rb1",
        Field("fradiobuttons").is_any_of("rb1", "rb2"),
    ) == [
        custom(FRADIOBUTTONS, "=", RB1),
        custom(FRADIOBUTTONS, "is_any_of", [RB1, RB2]),
    ]


def test_status_field_conditions():
    assert filter_dicts(
        Field("fstatus") == "s1",
    ) == [
        custom(FSTATUS, "=", S1),
    ]


def test_yesnomaybe_field_conditions():
    assert filter_dicts(
        Field("fyesnomaybe") == "Yes",
        Field("fyesnomaybe").is_any_of("Yes", "Maybe"),
    ) == [
        custom(FYESNOMAYBE, "=", YNM_YES),
        custom(FYESNOMAYBE, "is_any_of", [YNM_YES, YNM_MAYBE]),
    ]


# ---------------------------------------------------------------------------
# rating
# ---------------------------------------------------------------------------


def test_rating_field_conditions():
    # rating values are the numbers as strings, NOT option uuids
    assert filter_dicts(
        Field("frating") == 3,
        Field("frating") != 3,
        Field("frating") > 3,
        Field("frating") >= 3,
        Field("frating") < 3,
        Field("frating") <= 3,
        Field("frating").is_any_of(2, 4),
        Field("frating").not_any_of(2, 4),
        Field("frating").is_blank(),
        Field("frating").not_blank(),
    ) == [
        custom(FRATING, "=", "3"),
        custom(FRATING, "!=", "3"),
        custom(FRATING, ">", "3"),
        custom(FRATING, ">=", "3"),
        custom(FRATING, "<", "3"),
        custom(FRATING, "<=", "3"),
        custom(FRATING, "is_any_of", ["2", "4"]),
        custom(FRATING, "is_none_of", ["2", "4"]),
        custom(FRATING, "is_blank", True),
        custom(FRATING, "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# numbers: integer / decimal / money
# ---------------------------------------------------------------------------


def test_integer_field_conditions():
    assert filter_dicts(
        Field("finteger") == 42,
        Field("finteger") != 42,
        Field("finteger") > 42,
        Field("finteger") >= 42,
        Field("finteger") < 42,
        Field("finteger") <= 42,
        Field("finteger").between(1, 5),
        Field("finteger").is_blank(),
        Field("finteger").not_blank(),
    ) == [
        custom(FINTEGER, "=", 42),
        custom(FINTEGER, "!=", 42),
        custom(FINTEGER, ">", 42),
        custom(FINTEGER, ">=", 42),
        custom(FINTEGER, "<", 42),
        custom(FINTEGER, "<=", 42),
        custom(FINTEGER, "between", [1, 5]),
        custom(FINTEGER, "is_blank", True),
        custom(FINTEGER, "is_blank", False),
    ]


def test_decimal_field_conditions():
    assert filter_dicts(
        Field("fdecimal") == 1.5,
        Field("fdecimal").between(1, 5),
    ) == [
        custom(FDECIMAL, "=", 1.5),
        custom(FDECIMAL, "between", [1, 5]),
    ]


def test_price_field_conditions():
    assert filter_dicts(
        Field("fprice") == 9.99,
        Field("fprice") > 9.99,
    ) == [
        custom(FPRICE, "=", 9.99),
        custom(FPRICE, ">", 9.99),
    ]


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------


def test_files_field_conditions():
    # UI: None → is_blank true; One Or More → ">=" 1; More/Less Than # → ">"/"<"
    assert filter_dicts(
        Field("ffiles").is_blank(),
        Field("ffiles") >= 1,
        Field("ffiles") > 3,
        Field("ffiles") < 3,
    ) == [
        custom(FFILES, "is_blank", True),
        custom(FFILES, ">=", 1),
        custom(FFILES, ">", 3),
        custom(FFILES, "<", 3),
    ]


# ---------------------------------------------------------------------------
# date / datetime
# ---------------------------------------------------------------------------


def test_date_field_conditions():
    assert filter_dicts(
        Field("fdate") == date(2024, 12, 31),
        Field("fdate") != date(2024, 12, 31),
        Field("fdate").earlier_than(date(2024, 12, 31)),
        Field("fdate").earlier_than_or_on(date(2024, 12, 31)),
        Field("fdate").later_than(date(2024, 12, 31)),
        Field("fdate").later_than_or_on(date(2024, 12, 31)),
        Field("fdate").between(date(2024, 12, 1), date(2024, 12, 7)),
        Field("fdate").month_equals(3),
        Field("fdate").is_blank(),
        Field("fdate").not_blank(),
    ) == [
        custom(FDATE, "=", "2024-12-31"),
        custom(FDATE, "!=", "2024-12-31"),
        custom(FDATE, "<", "2024-12-31"),
        custom(FDATE, "<=", "2024-12-31"),
        custom(FDATE, ">", "2024-12-31"),
        custom(FDATE, ">=", "2024-12-31"),
        custom(FDATE, "between", ["2024-12-01", "2024-12-07"]),
        custom(FDATE, "month_equals", 3),
        custom(FDATE, "is_blank", True),
        custom(FDATE, "is_blank", False),
    ]


def test_datetime_field_conditions():
    # UI sends ISO-8601 UTC with milliseconds, e.g. "2024-12-31T06:00:00.000Z"
    dt = datetime(2024, 12, 31, 6, 0, 0, tzinfo=UTC)
    assert filter_dicts(
        Field("fdatetime") == dt,
        Field("fdatetime").earlier_than(dt),
        Field("fdatetime").between(date(2026, 6, 10), date(2026, 6, 17)),
        Field("fdatetime").month_equals(3),
        Field("fdatetime").is_blank(),
        Field("fdatetime").not_blank(),
    ) == [
        custom(FDATETIME, "=", "2024-12-31T06:00:00.000Z"),
        custom(FDATETIME, "<", "2024-12-31T06:00:00.000Z"),
        custom(FDATETIME, "between", ["2026-06-10", "2026-06-17"]),
        custom(FDATETIME, "month_equals", 3),
        custom(FDATETIME, "is_blank", True),
        custom(FDATETIME, "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# team member
# ---------------------------------------------------------------------------


def test_teammember_field_conditions():
    assert filter_dicts(
        Field("fteammember") == ALEC,
        Field("fteammember") != ALEC,
        Field("fteammember").is_any_of(ALEC),
        Field("fteammember").not_any_of(ALEC),
        Field("fteammember").is_me(),
        Field("fteammember").is_blank(),
        Field("fteammember").not_blank(),
    ) == [
        custom(FTEAMMEMBER, "=", ALEC),
        custom(FTEAMMEMBER, "!=", ALEC),
        custom(FTEAMMEMBER, "is_any_of", [ALEC]),
        custom(FTEAMMEMBER, "is_none_of", [ALEC]),
        custom(FTEAMMEMBER, "=", "is_me"),
        custom(FTEAMMEMBER, "is_blank", True),
        custom(FTEAMMEMBER, "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# relationship
# ---------------------------------------------------------------------------


def test_relationship_field_conditions():
    # relationship "Contains"/"Does Not Contain" keep contains/!contains tokens
    # but take LIST values of related-record uuids; any-of maps to is_any_of.
    assert filter_dicts(
        Field("primary_contact_record_0fe888").contains(CONTACT_A),
        Field("primary_contact_record_0fe888").not_contains(CONTACT_A),
        Field("primary_contact_record_0fe888").is_any_of(CONTACT_A, CONTACT_B),
        Field("primary_contact_record_0fe888").not_any_of(CONTACT_A, CONTACT_B),
        Field("primary_contact_record_0fe888").is_blank(),
        Field("primary_contact_record_0fe888").not_blank(),
    ) == [
        custom(FRELATIONSHIP, "contains", [CONTACT_A]),
        custom(FRELATIONSHIP, "!contains", [CONTACT_A]),
        custom(FRELATIONSHIP, "is_any_of", [CONTACT_A, CONTACT_B]),
        custom(FRELATIONSHIP, "is_none_of", [CONTACT_A, CONTACT_B]),
        custom(FRELATIONSHIP, "is_blank", True),
        custom(FRELATIONSHIP, "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# default (non-custom) fields
# ---------------------------------------------------------------------------


def test_name_and_display_name():
    assert filter_dicts(
        Field("name") == "abc",
        Field("display_name").contains("xyz"),
    ) == [
        non_custom("name", "=", "abc"),
        non_custom("display_name", "contains", "xyz"),
    ]


def test_default_datetime_fields():
    # created / updated / actual_close_date are datetimes → ISO-8601 UTC values
    dt = datetime(2024, 12, 1, 6, 0, 0, tzinfo=UTC)
    assert filter_dicts(
        Field("created").earlier_than(dt),
        Field("updated").earlier_than(dt),
        Field("actual_close_date").later_than(dt),
    ) == [
        non_custom("created", "<", "2024-12-01T06:00:00.000Z"),
        non_custom("updated", "<", "2024-12-01T06:00:00.000Z"),
        non_custom("actual_close_date", ">", "2024-12-01T06:00:00.000Z"),
    ]


def test_default_date_and_number_fields():
    assert filter_dicts(
        Field("estimated_close_date") == date(2024, 12, 20),
        Field("entity_value") > 1000,
        Field("percentage_chance_to_close") < 50,
    ) == [
        non_custom("estimated_close_date", "=", "2024-12-20"),
        non_custom("entity_value", ">", 1000),
        non_custom("percentage_chance_to_close", "<", 50),
    ]


def test_owner_conditions():
    assert filter_dicts(
        Field("owner") == ALEC,
        Field("owner") != ALEC,
        Field("owner").is_any_of(ALEC),
        Field("owner").not_any_of(ALEC),
        Field("owner").is_me(),
    ) == [
        non_custom("owner", "=", ALEC),
        non_custom("owner", "!=", ALEC),
        non_custom("owner", "is_any_of", [ALEC]),
        non_custom("owner", "is_none_of", [ALEC]),
        non_custom("owner", "=", "is_me"),
    ]


# ---------------------------------------------------------------------------
# stage (special filter shape)
# ---------------------------------------------------------------------------


def test_stage_equality_conditions():
    assert filter_dicts(
        Field("stage") == "Stage 1",
        Field("stage") != "Stage 1",
        Field("stage").is_any_of("Stage 1"),
        Field("stage").not_any_of("Stage 1"),
    ) == [
        stage_filter("=", STAGE_1),
        stage_filter("!=", STAGE_1),
        stage_filter("is_any_of", [STAGE_1]),
        stage_filter("is_none_of", [STAGE_1]),
    ]


def test_stage_time_in_stage():
    assert filter_dicts(
        Field("stage").time_in_stage("Stage 1", more_than=5, units="days"),
        Field("stage").time_in_stage("Stage 1", less_than=2, units="days"),
    ) == [
        stage_filter(
            "time_in_stage",
            STAGE_1,
            comparison_condition=">",
            comparison_value="5",
            comparison_type="days",
        ),
        stage_filter(
            "time_in_stage",
            STAGE_1,
            comparison_condition="<",
            comparison_value="2",
            comparison_type="days",
        ),
    ]


def test_stage_entered_and_left():
    assert filter_dicts(
        Field("stage").entered_stage("Stage 1", later_than=date(2024, 12, 15)),
        Field("stage").entered_stage("Stage 1", on=date(2024, 12, 15)),
        Field("stage").left_stage("Stage 1", on=date(2024, 12, 16)),
        Field("stage").left_stage("Stage 1", earlier_than_or_on=date(2024, 12, 16)),
    ) == [
        stage_filter(
            "entered_stage",
            STAGE_1,
            comparison_condition=">",
            comparison_value="2024-12-15",
        ),
        stage_filter(
            "entered_stage",
            STAGE_1,
            comparison_condition="=",
            comparison_value="2024-12-15",
        ),
        stage_filter(
            "left_stage",
            STAGE_1,
            comparison_condition="=",
            comparison_value="2024-12-16",
        ),
        stage_filter(
            "left_stage",
            STAGE_1,
            comparison_condition="<=",
            comparison_value="2024-12-16",
        ),
    ]


# ---------------------------------------------------------------------------
# group structure (and/or nesting)
# ---------------------------------------------------------------------------


def test_single_set_any_structure():
    # captured: ANY within one set → {"and": false, "query": [{"and": false, ...}]}
    assert Any(
        Field("display_name").contains("xyz"),
        Field("name") == "abc",
    ).as_dict() == {
        "and": False,
        "query": [
            {
                "and": False,
                "filters": [
                    non_custom("display_name", "contains", "xyz"),
                    non_custom("name", "=", "abc"),
                ],
            }
        ],
    }


def test_two_sets_or_of_all_structure():
    # captured: set 1 toggled to ALL, sets joined with OR
    assert Any(
        All(
            Field("display_name").contains("xyz"),
            Field("name") == "abc",
        ),
        All(
            Field("ftext") == "zzz",
        ),
    ).as_dict() == {
        "and": False,
        "query": [
            {
                "and": True,
                "filters": [
                    non_custom("display_name", "contains", "xyz"),
                    non_custom("name", "=", "abc"),
                ],
            },
            {
                "and": True,
                "filters": [
                    custom(FTEXT, "=", "zzz"),
                ],
            },
        ],
    }


def test_operator_syntax_in_options():
    assert Any(
        Field("fdropdown") in Options("dd1", "dd2"),
        Field("fdropdown") not in Options("dd2", "dd3"),
    ).as_dict() == {
        "and": False,
        "query": [
            {
                "and": False,
                "filters": [
                    custom(FDROPDOWN, "is_any_of", [DD1, DD2]),
                    custom(FDROPDOWN, "is_none_of", [DD2, DD3]),
                ],
            }
        ],
    }
