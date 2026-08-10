"""
UI ↔ DSL parity tests for Contact-specific filters.

Contacts ("clients" in the code, object api_name client_client) offer filters
that custom objects don't. Captured from the v2 staging UI the same way as
tests/test_ui_filter_parity.py (see docs/ui_filter_capture.md):

1. Contact-specific FIELDS: email_status (slug values!), birthday, timezone,
   titles (default dynamictags).
2. Whole filter CATEGORIES with their own payload shapes:
   - Tags                 -> {"type": "tags", "subtype": "tag", "condition", "ids"}
   - Subscription Lists   -> {"type": "subscription_lists", "status", "subscription_list_ids"}
   - Messages             -> {"type": "library_messages", "operator", "event", "last_n_days"}
   - Interactions         -> {"type": "interactions", ...}

All uuids below were captured from the staging "Aalii" business.
"""

import pytest

from kizen_builder.filtering import (
    Any,
    Field,
    Interactions,
    Messages,
    SubscriptionLists,
    Tags,
    filter_context,
)

# Contact tag uuids (UI "Tags" category; /client/fields/<tags-field>/tags)
TAG_AAA = "93461390-af63-491b-a037-79ce5d5f63ec"
TAG_QWERT = "307d8a45-b8b2-4447-b31d-81e43c5292a0"

# Subscription list uuids (/subscription-list)
NEWSLETTER = "0437e7fe-35fc-4ad0-be20-5f83c38b5094"
MARKETING = "fd2d2d0d-c10c-4de7-9e2a-df693d78d412"


@pytest.fixture(autouse=True)
def contacts_context(kizen):
    with filter_context("client_client"):
        yield


def filter_dicts(*conditions):
    return [c.as_dict(parent=object()) for c in conditions]


def non_custom(field, condition, value):
    return {
        "type": "fields",
        "subtype": "non_custom",
        "field": field,
        "condition": condition,
        "value": value,
    }


# ---------------------------------------------------------------------------
# contact-specific fields
# ---------------------------------------------------------------------------


def test_email_status_field():
    # email_status values are snake_case slugs of the option names, NOT uuids
    assert filter_dicts(
        Field("email_status") == "Opted In",
        Field("email_status") != "Opted In",
        Field("email_status").is_any_of("Not Opted In", "Suppression List"),
        Field("email_status").not_any_of("Unsubscribed From All"),
    ) == [
        non_custom("email_status", "=", "opted_in"),
        non_custom("email_status", "!=", "opted_in"),
        non_custom("email_status", "is_any_of", ["not_opted_in", "suppression_list"]),
        non_custom("email_status", "is_none_of", ["unsubscribed_from_all"]),
    ]


def test_birthday_field():
    # birthday is a standard date field (incl. month_equals)
    from datetime import date

    assert filter_dicts(
        Field("birthday") == date(2024, 12, 31),
        Field("birthday").month_equals(3),
    ) == [
        non_custom("birthday", "=", "2024-12-31"),
        non_custom("birthday", "month_equals", 3),
    ]


def test_timezone_field():
    # timezone is a single-select whose option ids ARE the IANA names
    assert filter_dicts(
        Field("timezone") == "America/Chicago",
        Field("timezone") != "America/Chicago",
        Field("timezone").is_blank(),
        Field("timezone").not_blank(),
    ) == [
        non_custom("timezone", "=", "America/Chicago"),
        non_custom("timezone", "!=", "America/Chicago"),
        non_custom("timezone", "is_blank", True),
        non_custom("timezone", "is_blank", False),
    ]


# ---------------------------------------------------------------------------
# Tags category
# ---------------------------------------------------------------------------


def test_tags_filters():
    # UI: Has Tag / Doesn't Have Tag / Contains Any Of / Contains None Of /
    # Is Blank / Isn't Blank. Payload uses "ids" (no field/value keys);
    # blanks have no "ids" key at all.
    assert filter_dicts(
        Tags.has("aaa"),
        Tags.has_not("aaa"),
        Tags.any_of("aaa", "qwert"),
        Tags.none_of("aaa", "qwert"),
        Tags.is_blank(),
        Tags.not_blank(),
    ) == [
        {"type": "tags", "subtype": "tag", "condition": "has", "ids": [TAG_AAA]},
        {"type": "tags", "subtype": "tag", "condition": "has_not", "ids": [TAG_AAA]},
        {
            "type": "tags",
            "subtype": "tag",
            "condition": "has_any",
            "ids": [TAG_AAA, TAG_QWERT],
        },
        {
            "type": "tags",
            "subtype": "tag",
            "condition": "has_none",
            "ids": [TAG_AAA, TAG_QWERT],
        },
        {"type": "tags", "subtype": "tag", "condition": "is_blank"},
        {"type": "tags", "subtype": "tag", "condition": "is_not_blank"},
    ]


# ---------------------------------------------------------------------------
# Subscription Lists category
# ---------------------------------------------------------------------------


def test_subscription_list_filters():
    def sl(status, ids):
        return {
            "type": "subscription_lists",
            "subtype": "subscription_list",
            "status": status,
            "subscription_list_ids": ids,
        }

    assert filter_dicts(
        SubscriptionLists.is_opted_in("Newsletter"),
        SubscriptionLists.is_not_opted_in("Newsletter"),
        SubscriptionLists.is_opted_out_of("Newsletter"),
        SubscriptionLists.opted_in_to_any_of("Marketing Content", "Newsletter"),
        SubscriptionLists.opted_in_to_none_of("Newsletter"),
    ) == [
        sl("is_opted_in", [NEWSLETTER]),
        sl("is_not_opted_in", [NEWSLETTER]),
        sl("is_opted_out_of", [NEWSLETTER]),
        sl("opted_in_to_any_of", [MARKETING, NEWSLETTER]),
        sl("opted_in_to_none_of", [NEWSLETTER]),
    ]


# ---------------------------------------------------------------------------
# Messages category
# ---------------------------------------------------------------------------


def test_message_filters():
    def msg(operator, event, last_n_days=None):
        return {
            "type": "library_messages",
            "subtype": "sent_messages",
            "operator": operator,
            "event": event,
            "last_n_days": last_n_days,
        }

    assert filter_dicts(
        Messages.sent(),
        Messages.not_sent(),
        Messages.delivered(),
        Messages.not_delivered(),
        Messages.opened(),
        Messages.didnt_open(last_n_days=30),
        Messages.clicked_link(),
        Messages.didnt_click_link(),
        Messages.opened_attachment(),
        Messages.didnt_open_attachment(),
        Messages.unsubscribed(),
        Messages.complained(),
        Messages.bounced(),
    ) == [
        msg("has_matches", "sent"),
        msg("has_no_matches", "sent"),
        msg("has_matches", "delivered"),
        msg("has_no_matches", "delivered"),
        msg("has_matches", "opened"),
        msg("has_no_matches", "opened", "30"),
        msg("has_matches", "clicked"),
        msg("has_no_matches", "clicked"),
        msg("has_matches", "attachment_opened"),
        msg("has_no_matches", "attachment_opened"),
        msg("has_matches", "unsubscribed"),
        msg("has_matches", "complained"),
        msg("has_matches", "bounced"),
    ]


# ---------------------------------------------------------------------------
# Interactions category
# ---------------------------------------------------------------------------


def test_interaction_filters():
    assert filter_dicts(
        Interactions.has_interaction_at_url(),
        Interactions.no_interaction_at_url(),
        Interactions.has_interaction_at_url(contains="example.com"),
    ) == [
        {
            "type": "interactions",
            "subtype": "interactions",
            "occurrence_condition": "atleast_one",
            "interaction_type_condition": "has_any",
            "payload": {"occurrence_condition": {"type": "has_any"}},
            "data_condition": "any",
        },
        {
            "type": "interactions",
            "subtype": "interactions",
            "occurrence_condition": "atleast_one",
            "interaction_type_condition": "has_none",
            "payload": {"occurrence_condition": {"type": "has_none"}},
            "data_condition": "any",
        },
        {
            "type": "interactions",
            "subtype": "interactions",
            "occurrence_condition": "atleast_one",
            "interaction_type_condition": "has_any",
            "payload": {
                "occurrence_condition": {"type": "has_any"},
                "field_conditions": {
                    "kznjs_url": {"condition": "contains", "value": "example.com"}
                },
            },
            "data_condition": "contains",
            "timeframe_condition": "any",
            "data_value": "example.com",
        },
    ]


# ---------------------------------------------------------------------------
# mixing contact filters with field filters in groups
# ---------------------------------------------------------------------------


def test_contact_filters_mix_with_field_filters():
    assert Any(
        Field("email_status") == "Opted In",
        Tags.has("aaa"),
    ).as_dict() == {
        "and": False,
        "query": [
            {
                "and": False,
                "filters": [
                    non_custom("email_status", "=", "opted_in"),
                    {
                        "type": "tags",
                        "subtype": "tag",
                        "condition": "has",
                        "ids": [TAG_AAA],
                    },
                ],
            }
        ],
    }
