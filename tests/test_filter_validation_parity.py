"""
The DSL raises informative errors for filters that cannot be expressed in
the Kizen UI (field-type × condition combinations outside the captured
condition tables in docs/ui_filter_capture.md).
"""

import pytest

from kizen_builder.filtering import Field, filter_context


@pytest.fixture(autouse=True)
def policies_context(kizen):
    with filter_context("policies_policy"):
        yield


def assert_not_supported(condition_obj, *expected_fragments):
    with pytest.raises(ValueError) as exc:
        condition_obj.as_dict(parent=object())
    message = str(exc.value)
    assert "does not support" in message
    for fragment in expected_fragments:
        assert fragment in message, f"{fragment!r} not in error: {message}"


def test_text_field_rejects_numeric_conditions():
    assert_not_supported(Field("ftext") < 5, "'<'", "'ftext'", "'text'")
    assert_not_supported(Field("ftext").between(1, 5), "'between'")
    assert_not_supported(Field("ftext").month_equals(3), "'month_equals'")


def test_longtext_only_supports_blank():
    assert_not_supported(Field("flongtext").contains("abc"), "'contains'", "'longtext'")
    assert_not_supported(Field("flongtext") == "abc", "'='")
    # the error message lists what IS allowed
    with pytest.raises(ValueError) as exc:
        (Field("flongtext") == "abc").as_dict(parent=object())
    assert "Supported conditions: is_blank" in str(exc.value)


def test_phonenumber_rejects_affix_conditions():
    assert_not_supported(Field("fphonenumber").startswith("512"), "'starts_with'")
    assert_not_supported(Field("fphonenumber") != "555", "'!='")


def test_checkbox_only_supports_checked():
    assert_not_supported(Field("fcheckbox").is_blank(), "'is_blank'", "'checkbox'")
    assert_not_supported(Field("fcheckbox").contains("x"), "'contains'")


def test_checkboxes_reject_has_all_and_has_none():
    # the UI has no "contains all of" / checkbox-style has_none conditions
    assert_not_supported(Field("fcheckboxes").has_all("cb1", "cb2"), "'has_all'")
    assert_not_supported(Field("fcheckboxes").has_none("cb1"), "'has_none'")
    assert_not_supported(Field("fcheckboxes").startswith("cb"), "'starts_with'")


def test_single_select_rejects_contains():
    assert_not_supported(Field("fdropdown").contains("dd1"), "'contains'", "'dropdown'")
    assert_not_supported(Field("fdropdown") > "dd1", "'>'")


def test_timezone_rejects_any_of(kizen):
    with filter_context("client_client"):
        assert_not_supported(
            Field("timezone").is_any_of("GMT"), "'is_any_of'", "'timezone'"
        )


def test_rating_rejects_between():
    assert_not_supported(Field("frating").between(1, 5), "'between'", "'rating'")


def test_files_reject_equals():
    assert_not_supported(Field("ffiles") == 3, "'='", "'files'")


def test_date_rejects_text_conditions():
    assert_not_supported(Field("fdate").contains("2024"), "'contains'", "'date'")


def test_team_member_rejects_contains():
    assert_not_supported(Field("fteammember").contains("alec"), "'contains'")


def test_relationship_rejects_equals():
    assert_not_supported(
        Field("primary_contact_record_0fe888") == "x", "'='", "'relationship'"
    )


def test_default_fields_without_blank_conditions():
    # created/updated/owner have no Is Blank / Isn't Blank in the UI
    assert_not_supported(Field("created").is_blank(), "'is_blank'", "'created'")
    assert_not_supported(Field("updated").not_blank(), "'is_blank'", "'updated'")
    assert_not_supported(Field("owner").is_blank(), "'is_blank'", "'owner'")


def test_stage_conditions():
    assert_not_supported(Field("stage").contains("Stage 1"), "'contains'", "'stage'")
    assert_not_supported(Field("stage").is_blank(), "'is_blank'")


def test_email_status_rejects_blank(kizen):
    with filter_context("client_client"):
        assert_not_supported(
            Field("email_status").is_blank(), "'is_blank'", "'email_status'"
        )


def test_unknown_field_raises_informative_error():
    with pytest.raises(ValueError) as exc:
        (Field("no_such_field") == "x").as_dict(parent=object())
    assert "Unknown field 'no_such_field'" in str(exc.value)
