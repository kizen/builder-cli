from datetime import date, timedelta

import pytest

from kizen_builder.filtering import All, Any, Field, Options, filter_context


@pytest.mark.live
def test_building_filters(kizen):
    with filter_context("client_client"):
        filter = All(
            Field("first_name") == "Jack",
            Field("created") < date(2024, 12, 6) - timedelta(days=5),
            Field("will_attend_webinar") not in Options("no", "maybe"),
            Any(
                Field("will_attend_webinar") in Options("yes", "maybe"),
                Field("attended_webinar") == "yes",
            ),
        )
        assert filter.as_dict() == {
            "and": True,
            "query": [
                {
                    "and": True,
                    "filters": [
                        {
                            "type": "fields",
                            "subtype": "non_custom",
                            "field": "first_name",
                            "condition": "=",
                            "value": "Jack",
                        },
                        {
                            "type": "fields",
                            "subtype": "non_custom",
                            "field": "created",
                            "condition": "<",
                            "value": "2024-12-01",
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            # "field": "will_attend_webinar",
                            "field": '"custom"::40e6737e-89e2-4b5d-8985-899d8fbd6ef3',
                            "condition": "is_none_of",
                            # "value": ["yes", "maybe"],
                            "value": [
                                "9fca6058-1d15-4f2f-b476-0156f36f7bd5",
                                "d123998a-7f41-4ddd-8e10-78b0219d5746",
                            ],
                        },
                    ],
                },
                {
                    "and": False,
                    "filters": [
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            # "field": "will_attend_webinar",
                            "field": '"custom"::40e6737e-89e2-4b5d-8985-899d8fbd6ef3',
                            "condition": "is_any_of",
                            # "value": ["yes", "maybe"],
                            "value": [
                                "98113345-5a84-4297-ace0-d4ad0cc0930b",
                                "d123998a-7f41-4ddd-8e10-78b0219d5746",
                            ],
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            # "field": "attended_webinar",
                            "field": '"custom"::063f8709-2ae0-44e3-b1b9-8cd4c0b67403',
                            "condition": "=",
                            "value": True,
                        },
                    ],
                },
            ],
        }


def test_generating_a_big_filter():
    All(
        Field("name") == "abc",
        Field("name") != "abc",
        Field("name").equals("abc"),
        Field("name").not_equals("abc"),
        "abc" in Field("name"),
        Field("name").contains("abc"),
        Field("name").not_contains("abc"),
        Field("name").startswith("abc"),
        Field("name").endswith("abc"),
        Field("name").not_startswith("abc"),
        Field("name").not_endswith("abc"),
        Field("name").is_blank(),
        Field("name").not_blank(),
        Field("mytextfield") == "abc",
        Field("mytextfield") != "abc",
        "abc" in Field("mytextfield"),
        Field("mytextfield").contains("abc"),
        Field("mytextfield").not_contains("abc"),
        Field("mytextfield").startswith("abc"),
        Field("mytextfield").endswith("abc"),
        Field("mytextfield").not_startswith("abc"),
        Field("mytextfield").not_endswith("abc"),
        Field("mytextfield").is_blank(),
        Field("mytextfield").not_blank(),
        # These should also all take datetime.date objects
        Field("date_created") == "2024-12-31",
        Field("date_created") != "2024-12-31",
        Field("date_created") < "2024-12-31",
        Field("date_created") <= "2024-12-31",
        Field("date_created") > "2024-12-31",
        Field("date_created") >= "2024-12-31",
        Field("date_created").equals("2024-12-31"),
        Field("date_created").not_equals("2024-12-31"),
        Field("date_created").earlier_than("2024-12-31"),
        Field("date_created").earlier_than_or_on("2024-12-31"),
        Field("date_created").later_than("2024-12-31"),
        Field("date_created").later_than_or_on("2024-12-31"),
        Field("date_created").between("2024-12-01", "2024-12-07"),
        # not implemented?
        Field("date_created").is_blank(),
        Field("date_created").not_blank(),
        Field("yesnomaybe") == "yes",
        Field("yesnomaybe") != "yes",
        Field("yesnomaybe").equals("yes"),
        Field("yesnomaybe").not_equals("no"),
        Field("yesnomaybe").is_any_of("yes", "maybe"),
        Field("yesnomaybe").not_any_of("yes", "maybe"),
        Field("yesnomaybe").is_blank(),
        Field("yesnomaybe").not_blank(),
        Field("owner") == "james@example.com",
        Field("owner") != "james@example.com",
        Field("owner") in Options("james@example.com", "chuck@example.com"),
        Field("owner") not in Options("james@example.com", "chuck@example.com"),
        Field("owner").equals("james@example.com"),
        Field("owner").not_equals("james@example.com"),
        Field("owner").is_any_of("james@example.com", "chuck@example.com"),
        Field("owner").not_any_of("james@example.com", "chuck@example.com"),
        Field("owner").is_me(),
        Field("stage") == "Stage 1",
        Field("stage") != "Stage 1",
        Field("stage").is_blank(),
        Field("stage").not_blank(),
        Field("tags").has_any("tag1", "tag2"),
        Field("tags").has_all("tag1", "tag2"),
        Field("tags").has_none("tag1", "tag2"),
    )


@pytest.mark.live
def test_filtering_user_api(kizen):
    kizen.CustomObject("client_client").filter_records(
        All(
            Field("first_name") == "Jack",
            Field("created") < date(2024, 12, 6) - timedelta(days=5),
            Field("will_attend_webinar") not in Options("no", "maybe"),
            Any(
                Field("will_attend_webinar") in Options("yes", "maybe"),
                Field("attended_webinar") == "yes",
            ),
        ),
        fields=[
            "first_name",
            "created",
            "will_attend_webinar",
            "attended_webinar",
            "email",
            "last_purchase_date",
        ],
    )


@pytest.mark.live
def test_checkboxes_filter(kizen):
    co = kizen.CustomObject("policies_policy")
    with filter_context(co.id):
        filterobj_methods = Any(
            Field("fcheckboxes").contains("cb1"),
            Field("fcheckboxes").not_contains("cb2"),
            Field("fcheckboxes").is_any_of("cb1", "cb2"),
            Field("fcheckboxes").not_any_of("cb2", "cb3"),
            Field("fcheckboxes").is_blank(),
            Field("fcheckboxes").not_blank(),
        )

        assert filterobj_methods.as_dict() == {
            "and": False,
            "query": [
                {
                    "and": False,
                    "filters": [
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            "field": '"custom"::88171c43-d47b-4706-aa10-4bf2f1b4d4ef',
                            "condition": "has",
                            "value": ["2a795c26-9478-4da8-bc22-5aba5497ea84"],
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            "field": '"custom"::88171c43-d47b-4706-aa10-4bf2f1b4d4ef',
                            "condition": "!has",
                            "value": ["e5c62880-fe99-43d1-ad20-5f3c93e28072"],
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            "field": '"custom"::88171c43-d47b-4706-aa10-4bf2f1b4d4ef',
                            "condition": "has_any",
                            "value": [
                                "2a795c26-9478-4da8-bc22-5aba5497ea84",
                                "e5c62880-fe99-43d1-ad20-5f3c93e28072",
                            ],
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            "field": '"custom"::88171c43-d47b-4706-aa10-4bf2f1b4d4ef',
                            "condition": "!has_any",
                            "value": [
                                "e5c62880-fe99-43d1-ad20-5f3c93e28072",
                                "df9c540d-d41c-450f-b94c-5b66a5d93e67",
                            ],
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            "field": '"custom"::88171c43-d47b-4706-aa10-4bf2f1b4d4ef',
                            "condition": "is_blank",
                            "value": True,
                        },
                        {
                            "type": "fields_v2",
                            "subtype": "custom",
                            "field": '"custom"::88171c43-d47b-4706-aa10-4bf2f1b4d4ef',
                            "condition": "is_blank",
                            "value": False,
                        },
                    ],
                }
            ],
        }

        filterobj = Any(
            Field("fcheckboxes") == "cb1",
            Field("fcheckboxes") != "cb2",
            Field("fcheckboxes") in Options("cb1", "cb2"),
            Field("fcheckboxes") not in Options("cb2", "cb3"),
            Field("fcheckboxes") == [],
            Field("fcheckboxes") != [],
        )
        assert filterobj_methods.as_dict() == filterobj.as_dict()


@pytest.mark.live
def test_checkbox_filter(kizen):
    co = kizen.CustomObject("policies_policy")
    with filter_context(co.id):
        filterobj_methods = Any(
            Field("fcheckbox").is_checked(),
            Field("fcheckbox").not_checked(),
        )
        assert filterobj_methods.as_dict() == {
            "and": False,
            "query": [
                {
                    "and": False,
                    "filters": [
                        {
                            "condition": "=",
                            "field": '"custom"::fdaadc16-bc4b-4cc0-bee0-609b84c12293',
                            "subtype": "custom",
                            "type": "fields_v2",
                            "value": True,
                        },
                        {
                            "condition": "=",
                            "field": '"custom"::fdaadc16-bc4b-4cc0-bee0-609b84c12293',
                            "subtype": "custom",
                            "type": "fields_v2",
                            "value": False,
                        },
                    ],
                }
            ],
        }

        filterobj = Any(
            Field("fcheckbox") == True,  # noqa: E712 — exercises Field.__eq__ sugar, not a real bool check
            Field("fcheckbox") == False,  # noqa: E712 — same
        )

        assert filterobj.as_dict() == filterobj_methods.as_dict()

        filterobj2 = Any(
            Field("fcheckbox") == "yes",
            Field("fcheckbox") == "no",
        )

        assert filterobj2.as_dict() == filterobj_methods.as_dict()

        filterobj3 = Any(
            Field("fcheckbox") == "checked",
            Field("fcheckbox") == "",
        )

        assert filterobj3.as_dict() == filterobj_methods.as_dict()
