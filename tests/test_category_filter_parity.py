"""
UI ↔ DSL parity tests for the non-field filter CATEGORIES available on
custom objects (most also exist on Contacts): Lead Sources, Logged
Activities, Scheduled Activities, Team Interactions, Agentic Workflows,
and Related Object.

Captured from the v2 staging UI on the Policies object the same way as the
other parity suites (see docs/ui_filter_capture.md). Forms and Surveys could
not be captured (no forms/surveys exist in the staging business).
"""

from datetime import date

import pytest

from kizen_builder.filtering import (
    AgenticWorkflows,
    All,
    Any,
    Field,
    Forms,
    LeadSources,
    LoggedActivities,
    RelatedObject,
    ScheduledActivities,
    Surveys,
    TeamInteractions,
    filter_context,
)

# uuids captured from staging (Aalii business)
NOTES_ACTIVITY = "e30f865a-e4f8-4a6b-a92f-3d29e9b54b73"
FRELATIONSHIP = "8cd45709-e199-4c7f-b193-d984e6bfe36a"  # primary_contact_record_0fe888
POLICY_FORM = "07961e99-70ed-4ddd-9ab6-2c17989c76e6"
POLICY_SURVEY = "ab823a7f-4a75-4546-aa75-129708e03313"
POLICY_FORM_NAME_FIELD = (
    "cc9ac489-b56d-47b9-81aa-04db0443363e"  # "Policy Name" on the form
)


@pytest.fixture(autouse=True)
def policies_context(kizen):
    with filter_context("policies_policy"):
        yield


def filter_dicts(*conditions):
    return [c.as_dict(parent=object()) for c in conditions]


# ---------------------------------------------------------------------------
# Lead Sources
# ---------------------------------------------------------------------------


def ls(condition_type, condition_value, source_type, **extra):
    payload = {
        "condition_type": condition_type,
        "condition_value": condition_value,
        "source_type": source_type,
    }
    payload.update(extra)
    return {"type": "lead_sources", "subtype": "lead_sources", "payload": payload}


def test_lead_source_filters():
    assert filter_dicts(
        LeadSources.first_source_is("organic_search"),
        LeadSources.first_source_is_not("organic_search"),
        LeadSources.last_source_is_not("google_ads"),
        LeadSources.any_source_is("direct_traffic"),
        LeadSources.no_source_is("direct_traffic"),
    ) == [
        ls("first_lead_source", True, "organic_search"),
        ls("first_lead_source", False, "organic_search"),
        ls("last_lead_source", False, "google_ads"),
        ls("any_lead_source", True, "direct_traffic"),
        ls("any_lead_source", False, "direct_traffic"),
    ]


def test_utm_lead_source_filters():
    # the UTM component being matched is the payload key
    assert filter_dicts(
        LeadSources.last_source_is_not("utm"),
        LeadSources.first_source_is("utm", equals="newsletter_link"),
        LeadSources.first_source_is("utm", no_value=True),
        LeadSources.first_source_is("utm", utm_type="campaign", no_value=True),
        LeadSources.first_source_is("utm", utm_type="campaign", equals="summer_promo"),
    ) == [
        ls("last_lead_source", False, "utm", source={"condition": "any"}),
        ls(
            "first_lead_source",
            True,
            "utm",
            source={"condition": "equals", "value": "newsletter_link"},
        ),
        ls("first_lead_source", True, "utm", source={"condition": "none"}),
        ls("first_lead_source", True, "utm", campaign={"condition": "none"}),
        ls(
            "first_lead_source",
            True,
            "utm",
            campaign={"condition": "equals", "value": "summer_promo"},
        ),
    ]


def test_custom_lead_source_filters():
    assert filter_dicts(
        LeadSources.first_source_is("custom"),
        LeadSources.first_source_is("custom", equals="partner_referral"),
    ) == [
        ls("first_lead_source", True, "custom", source={"condition": "any"}),
        ls(
            "first_lead_source",
            True,
            "custom",
            source={"condition": "equals", "value": "partner_referral"},
        ),
    ]


def test_lead_source_sub_condition_rejected_for_simple_sources():
    import pytest as _pytest

    with _pytest.raises(ValueError):
        LeadSources.first_source_is("organic_search", equals="x")
    with _pytest.raises(ValueError):
        LeadSources.first_source_is("utm", utm_type="bogus")


# ---------------------------------------------------------------------------
# Logged Activities
# ---------------------------------------------------------------------------


def test_logged_activity_filters():
    assert filter_dicts(
        LoggedActivities.submitted(),
        LoggedActivities.submitted(within_days=7, by="is_me"),
        LoggedActivities.not_submitted(by="is_me"),
        LoggedActivities.submitted(
            activity_id=NOTES_ACTIVITY,
            between=(date(2026, 6, 8), date(2026, 6, 11)),
        ),
    ) == [
        {
            "type": "activities",
            "subtype": "activity",
            "activity_type": "any",
            "payload": {
                "submitted": True,
                "time": {"past": None, "days": None},
                "by": {"team_member": None, "which": None},
            },
        },
        {
            "type": "activities",
            "subtype": "activity",
            "activity_type": "any",
            "payload": {
                "submitted": True,
                "time": {"past": True, "days": "7"},
                "by": {"team_member": True, "which": "is_me"},
            },
        },
        {
            "type": "activities",
            "subtype": "activity",
            "activity_type": "any",
            "payload": {
                "submitted": False,
                "by": {"team_member": True, "which": "is_me"},
            },
        },
        {
            "type": "activities",
            "subtype": "activity",
            "activity_type": "specific",
            "activity_object_id": NOTES_ACTIVITY,
            "payload": {
                "submitted": True,
                "time": {"date_range": ["2026-06-08", "2026-06-11"]},
                "by": {"team_member": None, "which": None},
            },
        },
    ]


# ---------------------------------------------------------------------------
# Scheduled Activities
# ---------------------------------------------------------------------------


def test_scheduled_activity_filters():
    def sa(scheduled_condition, **extra):
        d = {
            "type": "scheduled_activities",
            "subtype": "scheduled_activities",
            "activity_type": "any",
            "scheduled_condition": scheduled_condition,
        }
        d.update(extra)
        d.setdefault("assigned_condition", "any_member")
        return d

    assert filter_dicts(
        ScheduledActivities.scheduled_any_time(),
        ScheduledActivities.not_scheduled(),
        ScheduledActivities.scheduled_within_days(14),
        ScheduledActivities.overdue_more_than_days(3),
        ScheduledActivities.not_scheduled(assigned_to="is_me"),
        ScheduledActivities.due_between(
            date(2026, 6, 8), date(2026, 6, 11), assigned_to="is_me"
        ),
    ) == [
        sa("any_time"),
        sa("not_scheduled"),
        sa("within_n_days", n_days="14"),
        sa("overdue_more_than_n_days", n_days="3"),
        sa("not_scheduled", assigned_condition="specific_member", assigned_id="is_me"),
        sa(
            "between",
            date_range=["2026-06-08", "2026-06-11"],
            assigned_condition="specific_member",
            assigned_id="is_me",
        ),
    ]


# ---------------------------------------------------------------------------
# Team Interactions
# ---------------------------------------------------------------------------


def test_team_interaction_filters():
    assert filter_dicts(
        TeamInteractions.interacted_with(),
        TeamInteractions.interacted_with(within_days=5),
        TeamInteractions.not_interacted_with(within_days=5),
        TeamInteractions.not_interacted_with(member="is_me", within_days=5),
    ) == [
        {
            "type": "association",
            "interacted": True,
            "subtype": "team",
            "time_past": "None_True",
        },
        {
            "type": "association",
            "interacted": True,
            "subtype": "team",
            "time_past": "True_True",
            "past_n_days": "5",
        },
        {
            "type": "association",
            "interacted": False,
            "subtype": "team",
            "time_past": "True_True",
            "past_n_days": "5",
        },
        {
            "type": "association",
            "interacted": False,
            "subtype": "team",
            "with": "is_me",
            "time_past": "True_True",
            "past_n_days": "5",
        },
    ]


# ---------------------------------------------------------------------------
# Agentic Workflows
# ---------------------------------------------------------------------------

POLICY_WORKFLOW_1 = "c8297c7b-6ccd-4fd8-8576-310beccfe4f4"


def test_agentic_workflow_filters():
    # AgenticWorkflows(...) — the ellipsis literal — means "Any Agentic Workflow"
    def aw(status, **extra):
        d = {"type": "automation2", "subtype": "automation", "status": status}
        d.update(extra)
        return d

    assert filter_dicts(
        AgenticWorkflows(...).is_active(),
        AgenticWorkflows(...).is_paused(),
        AgenticWorkflows(...).was_never_active(),
        AgenticWorkflows(...).was_started(),
        AgenticWorkflows(...).status_any_of("cancelled", "completed"),
    ) == [
        aw("active"),
        aw("paused"),
        aw("never"),
        aw("was_started", time_period="any_time"),
        aw(["cancelled", "completed"]),
    ]


def test_specific_agentic_workflow_filters():
    # workflows can be referenced by name (resolved via the API) or uuid
    def aw(status, **extra):
        d = {
            "type": "automation2",
            "subtype": "automation",
            "automation_id": POLICY_WORKFLOW_1,
            "status": status,
        }
        d.update(extra)
        return d

    assert filter_dicts(
        AgenticWorkflows("policy_workflow_1").is_active(),
        AgenticWorkflows(POLICY_WORKFLOW_1).is_active(),
        AgenticWorkflows("policy_workflow_1").was_started(),
        AgenticWorkflows("policy_workflow_1").status_any_of("cancelled", "completed"),
    ) == [
        aw("active"),
        aw("active"),
        aw("was_started", time_period="any_time"),
        aw(["cancelled", "completed"]),
    ]


def test_unknown_agentic_workflow_raises_informative_error():
    import pytest as _pytest

    # display names are not accepted — use the api_name or uuid
    with _pytest.raises(ValueError) as exc:
        AgenticWorkflows("policy workflow 1").is_active().as_dict(parent=object())
    message = str(exc.value)
    assert "Unknown agentic workflow 'policy workflow 1'" in message
    assert "policy_workflow_1" in message  # suggests available api_names


# ---------------------------------------------------------------------------
# Forms and Surveys
# ---------------------------------------------------------------------------


def _form_dict(type_, subtype, form_id, submitted_condition, **payload_extra):
    payload = {
        "form_id": form_id,
        "type": type_,
        "subtype": subtype,
        "submitted_condition": submitted_condition,
    }
    payload.update(payload_extra)
    payload.setdefault("submission", "null")
    return {"form_id": form_id, "type": type_, "subtype": subtype, "payload": payload}


def test_form_filters():
    assert filter_dicts(
        Forms.submitted_any_time(POLICY_FORM),
        Forms.submitted_within_days(POLICY_FORM, 7),
        Forms.not_submitted_within_days(POLICY_FORM, 7),
        Forms.never_submitted(POLICY_FORM),
    ) == [
        _form_dict("forms_v2", "form", POLICY_FORM, "submitted_any_time"),
        _form_dict(
            "forms_v2", "form", POLICY_FORM, "submitted_past_n_days", n_days_value="7"
        ),
        _form_dict(
            "forms_v2",
            "form",
            POLICY_FORM,
            "submitted_not_past_n_days",
            n_days_value="7",
        ),
        _form_dict("forms_v2", "form", POLICY_FORM, "never_submitted"),
    ]


def test_form_filter_with_specific_answer():
    assert Forms.not_submitted_within_days(
        POLICY_FORM, 7, answer=(POLICY_FORM_NAME_FIELD, "contains", "Alaska")
    ).as_dict() == _form_dict(
        "forms_v2",
        "form",
        POLICY_FORM,
        "submitted_not_past_n_days",
        n_days_value="7",
        submission="with_specific_answer",
        field_id=POLICY_FORM_NAME_FIELD,
        answer={
            "field_id": POLICY_FORM_NAME_FIELD,
            "condition": "contains",
            "value": "Alaska",
        },
        condition="contains",
        value="Alaska",
    )


def test_survey_filters():
    # Surveys are identical to Forms except the type tokens
    assert filter_dicts(
        Surveys.submitted_any_time(POLICY_SURVEY),
        Surveys.submitted_within_days(POLICY_SURVEY, 7),
    ) == [
        _form_dict("surveys", "survey", POLICY_SURVEY, "submitted_any_time"),
        _form_dict(
            "surveys",
            "survey",
            POLICY_SURVEY,
            "submitted_past_n_days",
            n_days_value="7",
        ),
    ]


# ---------------------------------------------------------------------------
# Related Object (nested filters on related records)
# ---------------------------------------------------------------------------


def test_related_object_filter():
    assert RelatedObject.has_filters(
        "primary_contact_record_0fe888",
        Any(All(Field("first_name") == "Bob")),
        related_object="client_client",
    ).as_dict() == {
        "type": "related_object",
        "field_id": FRELATIONSHIP,
        "condition": "custom_filter",
        "subtype": "related_object_filter",
        "next_class_key": "fields",
        "value": {
            "and": False,
            "query": [
                {
                    "and": True,
                    "filters": [
                        {
                            "type": "fields",
                            "subtype": "non_custom",
                            "field": "first_name",
                            "condition": "=",
                            "value": "Bob",
                        }
                    ],
                }
            ],
        },
    }
