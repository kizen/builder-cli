"""Type-specific config blocks shared by field-like models
(FieldDef, ActivityFieldDef, FormFieldDef)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kizen_builder.models.spec._base import ApiName, RelationCardinality, RelationType


class RelationConfig(BaseModel):
    """Config for a `field_type: relationship` field."""

    model_config = ConfigDict(extra="forbid")

    target_object: ApiName = Field(
        description="api_name of the target custom object. Must exist in this spec."
    )
    relation_type: RelationType | RelationCardinality = Field(
        default="many_to_one",
        description=(
            "Cardinality/directionality of the relation. Prefer the clear "
            "cardinality names (one_to_one, many_to_one, one_to_many, "
            "many_to_many) — matches what Kizen's UI shows. The raw wire "
            "values (primary, additional, primary_for, additional_for) are "
            "also accepted for specs authored from live API output."
        ),
    )
    related_name: str | None = Field(
        default=None,
        description="Display label for the inverse relation on the target object.",
    )
    target_category: ApiName | None = Field(
        default=None,
        description=(
            "api_name of the field category on the target object where the inverse "
            "relation field should live. If omitted, Kizen picks a default."
        ),
    )


class MoneyConfig(BaseModel):
    """Config for a `field_type: money` field."""

    model_config = ConfigDict(extra="allow")

    currency: str = Field(
        default="USD",
        description="ISO 4217 currency code (e.g. USD, EUR, GBP).",
        min_length=3,
        max_length=3,
    )


class RatingConfig(BaseModel):
    """Config for a `field_type: rating` field."""

    model_config = ConfigDict(extra="allow")

    min_value: int = Field(default=1, ge=1, le=9)
    max_value: int = Field(default=5, ge=2, le=10)
    min_label: str = Field(default="Low", min_length=1)
    max_label: str = Field(default="High", min_length=1)

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.max_value <= self.min_value:
            raise ValueError("rating.max_value must be greater than min_value")
        return self


class DecimalConfig(BaseModel):
    """Config for a `field_type: decimal` field."""

    model_config = ConfigDict(extra="allow")

    min_value: float = 0
    max_value: float = 999999


class PhoneConfig(BaseModel):
    """Config for a `field_type: phonenumber` field."""

    model_config = ConfigDict(extra="allow")

    enable_extension: bool = False


class StatusOption(BaseModel):
    """An option on a pipeline `status` field."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    code: str | None = None
    status: Literal["open", "won", "lost", "disqualified"] = "open"
    percentage_chance_to_close: int | None = Field(default=None, ge=0, le=100)
