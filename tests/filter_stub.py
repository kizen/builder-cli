"""
Offline stub of the kizen Client for filter tests.

Field/option metadata below was captured from the live staging API
("Policies" object, business "Aalii") on 2026-06-10 — the same fixture
data the UI-parity capture in docs/ui_filter_capture.md was built against.

Used by the `kizen` fixture unless pytest is run with --online, so
kizen/filtering.py can be developed without network access or staging
credentials.
"""

POLICIES_OBJ_ID = "7cb5ce29-bf20-4f0f-bdc9-412a8c777ff8"
CONTACTS_OBJ_ID = "aba65b8f-946a-4113-8b69-cbbfb6257a1f"  # client_client

# name: (field_type, field_id, is_default, [(option_name, option_id), ...])
POLICIES_FIELDS = {
    "name": ("text", "2ec6f9d0-fc97-498c-aa6a-33a6bb917fdd", True, []),
    "created": ("datetime", "f0f10446-94b4-4088-9d18-587fd5b3fd2d", True, []),
    "stage": (
        "dropdown",
        "94de5e17-04f5-490d-9510-793e01d38ffa",
        True,
        [("Stage 1", "a82570ce-c4e4-4548-bbb7-8b77f94bbb9a")],
    ),
    "estimated_close_date": ("date", "d066ae47-a4c0-4f1f-9450-4acd320d0b68", True, []),
    "actual_close_date": ("datetime", "a37a486c-ccab-4408-9d13-d8772716b35f", True, []),
    "entity_value": ("money", "f1cbeea9-d8c8-4db9-83c6-a12b2f6b6c66", True, []),
    "percentage_chance_to_close": (
        "integer",
        "a6483973-d1ad-4ae6-a52a-d3b5681ae464",
        True,
        [],
    ),
    "owner": ("team_selector", "82e20732-8c19-48ad-9fef-8e417aa81801", True, []),
    "updated": ("datetime", "17256d80-3b97-4605-81b4-a72fdbfc2c46", True, []),
    "primary_contact_record_0fe888": (
        "relationship",
        "8cd45709-e199-4c7f-b193-d984e6bfe36a",
        False,
        [],
    ),
    "primary_for_commission_records_35a8fa": (
        "relationship",
        "ee1e9cda-e8c5-4591-8abe-718cb9001d98",
        False,
        [],
    ),
    "display_name": ("text", "33c9dea4-5034-4ecf-b877-c52fdef0e0a9", True, []),
    "fcheckbox": ("checkbox", "fdaadc16-bc4b-4cc0-bee0-609b84c12293", False, []),
    "fcheckboxes": (
        "checkboxes",
        "88171c43-d47b-4706-aa10-4bf2f1b4d4ef",
        False,
        [
            ("cb1", "2a795c26-9478-4da8-bc22-5aba5497ea84"),
            ("cb2", "e5c62880-fe99-43d1-ad20-5f3c93e28072"),
            ("cb3", "df9c540d-d41c-450f-b94c-5b66a5d93e67"),
        ],
    ),
    "fdate": ("date", "53a730c8-851b-4421-bbe7-cd4004ac052e", False, []),
    "fdatetime": ("datetime", "3d574c03-a420-4175-b64d-5bbdc3f02822", False, []),
    "fdropdown": (
        "dropdown",
        "cc3c8cac-d614-4850-b38d-55e9c8ba7ed4",
        False,
        [
            ("dd1", "82cd3986-8f04-4de3-acde-9c7f96aa73de"),
            ("dd2", "c93df865-825e-41f2-a6e2-e9e5cdabed61"),
            ("dd3", "1867428f-be13-48d1-b7c3-03647b83aeaf"),
        ],
    ),
    # NOTE: like the live API, dynamictags fields have NO "options" in their
    # field metadata — tags are resolved via Client.get_field_tags().
    "fdynamictags": ("dynamictags", "d9d3a405-42cb-4158-b15d-073ab2270893", False, []),
    "femail": ("email", "11c84d9f-1a28-467f-9260-6cb013d04846", False, []),
    "ffiles": ("files", "a70e1efc-f23e-4aaf-a39a-0b08f7814923", False, []),
    "flongtext": ("longtext", "2072621b-9dd3-4c54-aa0a-d35b8e829b9a", False, []),
    "fdecimal": ("decimal", "d88c9836-b82a-4862-b7d1-617b7c81629c", False, []),
    "finteger": ("integer", "6a5c68f0-71e0-4308-b62e-67d114c0e69b", False, []),
    "fphonenumber": ("phonenumber", "493c11cf-a357-4afa-b356-3c8d082832b3", False, []),
    "fprice": ("money", "695ad3e6-5a12-45b1-ae4a-c11472f7edd8", False, []),
    "fradiobuttons": (
        "radio",
        "186eb6e8-197f-44ed-a2c2-b67a8ea5a096",
        False,
        [
            ("rb1", "ff6aaf15-3c7b-430d-afdf-bf23f26267ff"),
            ("rb2", "82419070-4c69-4c5b-9181-e0442bfad14f"),
            ("rb3", "288b7c3a-71c5-4690-b931-056cba3481c0"),
        ],
    ),
    "frating": (
        "rating",
        "8f224ab8-b585-45f8-9b92-fc2fe1869aa2",
        False,
        [
            ("1 - Unsatisfied", "5d7e7351-a355-31d5-959e-28f9d99e4be0"),
            ("2", "d2b265d9-2be6-3cf1-9274-60f3a2ab319b"),
            ("3", "4a2d2b74-2814-38fa-9fe9-64be76a4a0af"),
            ("4", "9ebfd196-a7d4-3046-89a6-c34a0a0cfa69"),
            ("5 - Satisfied", "f7c3bbb6-4b13-3d6d-8054-2c1b4dbe5f94"),
        ],
    ),
    "fstatus": (
        "status",
        "0f5900a4-a799-4108-9010-12b3ba577d77",
        False,
        [
            ("s1", "a3559536-7a1a-4ea6-b282-4c0f0bc2a37b"),
            ("s2", "41e20520-b139-4162-88d2-5305529b8388"),
            ("s3", "e2d9b135-f971-42f1-97a0-3d597ed37523"),
        ],
    ),
    "fteammember": ("team_selector", "0a40f245-a9bd-47df-bf1c-8a88583d29c5", False, []),
    "ftext": ("text", "921cec5c-9f68-4cd1-bf30-b11f00571175", False, []),
    "fyesno": (
        "yesnomaybe",
        "a51afe14-2a80-4f6f-854f-f4ac21600da3",
        False,
        [
            ("Yes", "3f3f6e39-14b0-4f38-95f1-26cde90e92a4"),
            ("No", "1c0943fe-7356-401b-b947-187a15028c0a"),
        ],
    ),
    "fyesnomaybe": (
        "yesnomaybe",
        "2f27f7a1-f957-4ff8-b16c-aa69fee899d9",
        False,
        [
            ("Yes", "f27f237d-f397-4a49-832d-83b2b79bc5f9"),
            ("No", "117f2314-b9c5-4fc6-aa95-faf10ca96d11"),
            ("Maybe", "2c0de3ff-87f3-4510-9596-6ac832cfeaae"),
        ],
    ),
}


# Contacts (client_client) default fields, captured from staging.
# NOTE: email_status is a dropdown whose filter VALUES are snake_case slugs of
# the option names, not the option uuids. timezone options use the IANA name
# as both name and id. titles/tags are default dynamictags fields.
CONTACT_FIELDS = {
    "first_name": ("text", "aa723f3b-712c-4a1a-8aa1-51947e0c40a5", True, []),
    "last_name": ("text", "2b83c5b6-cc72-4e60-868b-9d4791bfd83e", True, []),
    "email": ("email", "b4d10b1e-ca71-4a7f-ba2a-4852a36dcb1a", True, []),
    "email_status": (
        "dropdown",
        "fa552525-55ff-408f-a87e-a7d7526602a7",
        True,
        [
            ("Opted In", "820c3454-c9b3-4430-b722-ed89841876c3"),
            ("Not Opted In", "e2e84b7b-515a-4ee7-84d0-9ca1e4f9cc8e"),
            ("Unsubscribed From All", "4b9c958f-7faa-4f2f-bbc6-9c41ec7e6de0"),
            ("Suppression List", "9abacb17-a931-44ef-a37f-d5bba9529bff"),
        ],
    ),
    "birthday": ("date", "3db2e2cc-45a0-4bbf-9119-4658e38dc61a", True, []),
    "timezone": (
        "timezone",
        "79633fe5-96cc-4b47-b87b-ab2c25510f85",
        True,
        [
            ("US/Central", "US/Central"),
            ("America/Chicago", "America/Chicago"),
            ("GMT", "GMT"),
        ],
    ),
    "titles": ("dynamictags", "a37ef985-7daa-46a3-bd67-2bca894e98de", True, []),
    "tags": ("dynamictags", "894e688e-3c1f-4107-bb89-5b347fbab132", True, []),
}

# Contact tags (the UI's "Tags" filter category), served by
# /client/fields/<tags-field-id>/tags (captured from staging).
CONTACT_TAGS = [
    ("aaa", "93461390-af63-491b-a037-79ce5d5f63ec"),
    ("qwert", "307d8a45-b8b2-4447-b31d-81e43c5292a0"),
]

# Subscription lists, served by /subscription-list (captured from staging).
SUBSCRIPTION_LISTS = [
    ("Marketing Content", "fd2d2d0d-c10c-4de7-9e2a-df693d78d412"),
    ("Customer Updates", "3664655b-c241-4a92-9be8-cac950446b45"),
    ("Newsletter", "0437e7fe-35fc-4ad0-be20-5f83c38b5094"),
    ("Survey Reminders & Follow Up", "6c06c053-c74a-492a-9c07-bbc5b363d067"),
    ("Event Reminders & Follow Up", "83ba46fb-9a9a-4d8f-bc21-cba9d0bccd93"),
]


# Agentic workflows (automations), served by
# /automation2/automations?custom_object_id=<obj> (captured from staging).
# (name, api_name, id)
AGENTIC_WORKFLOWS = {
    POLICIES_OBJ_ID: [
        (
            "policy workflow 1",
            "policy_workflow_1",
            "c8297c7b-6ccd-4fd8-8576-310beccfe4f4",
        ),
        (
            "policy workflow 2",
            "policy_workflow_2",
            "8e9a91e3-5a7d-4de7-bcc4-ff40b5ae989c",
        ),
    ],
}


# Tags for dynamictags fields, served by the /pipelines/<obj>/fields/<field>/tags
# endpoint (captured from staging).
FIELD_TAGS = {
    "d9d3a405-42cb-4158-b15d-073ab2270893": [  # fdynamictags
        ("dt1", "5afe6e1c-8d1a-4e22-9be0-7bf08fd57cfd"),
        ("dt2", "631ac69a-9718-4af7-b95f-3c561cf50a62"),
        ("dt3", "0aedc479-08ad-46f9-bf5a-004028514663"),
    ],
}


class StubClient:
    """Implements the subset of kizen.Client that kizen/filtering.py uses."""

    def custom_object(self, api_name):
        if api_name in (CONTACTS_OBJ_ID, "client_client"):
            return {
                "id": CONTACTS_OBJ_ID,
                "api_name": "client_client",
                "name": "client_client",
            }
        return {"id": POLICIES_OBJ_ID, "api_name": api_name, "name": api_name}

    def get_field_tags(self, object_id, field_id, search=""):
        return [
            {"id": i, "name": n}
            for n, i in FIELD_TAGS.get(field_id, [])
            if search.lower() in n.lower()
        ]

    def get_contact_tags(self, search=""):
        return [
            {"id": i, "name": n} for n, i in CONTACT_TAGS if search.lower() in n.lower()
        ]

    def get_subscription_lists(self):
        return [{"id": i, "name": n} for n, i in SUBSCRIPTION_LISTS]

    def get_agentic_workflows(self, object_id, search=""):
        return [
            {"id": i, "name": n, "api_name": a}
            for n, a, i in AGENTIC_WORKFLOWS.get(object_id, [])
            if search.lower() in n.lower()
        ]

    def get_field(self, obj_id, name):
        fields = CONTACT_FIELDS if obj_id == CONTACTS_OBJ_ID else POLICIES_FIELDS
        if name not in fields:
            return None
        field_type, field_id, is_default, options = fields[name]
        return {
            "name": name,
            "id": field_id,
            "field_type": field_type,
            "is_default": is_default,
            "options": [{"name": n, "id": i} for n, i in options],
        }
