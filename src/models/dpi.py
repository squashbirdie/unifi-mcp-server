"""Deep Packet Inspection (DPI) models."""

from pydantic import BaseModel, ConfigDict, Field


class DPICategory(BaseModel):
    """DPI category model.

    Field shape corrected against a live response from the local Integration
    API (Network 10.5.67, GET .../dpi/categories): plain `id` (an int, e.g.
    `{"id": 0, "name": "Instant messengers"}`) — NOT the Mongo-style `_id`
    string this model previously required, which made every category fail
    Pydantic validation.
    """

    id: int | str = Field(..., description="Category identifier")
    name: str = Field(..., description="Category name")
    description: str | None = Field(None, description="Category description")

    # Application count
    app_count: int | None = Field(None, description="Number of applications in this category")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class DPIApplication(BaseModel):
    """DPI application model.

    Field shape corrected against a live response from the local Integration
    API (Network 10.5.67, GET .../dpi/applications): entries are just
    `{"id": <int>, "name": <str>}` — no `_id`, `category_id`, `enabled`,
    `protocols` or `ports` at this endpoint, so those are now optional
    instead of required (they were making every application fail validation).
    """

    id: int | str = Field(..., description="Application identifier")
    name: str = Field(..., description="Application name")
    category_id: str | int | None = Field(None, description="Category identifier")
    category_name: str | None = Field(None, description="Category name")

    # Application metadata
    enabled: bool | None = Field(None, description="Whether application detection is enabled")

    # Traffic classification
    protocols: list[str] = Field(
        default_factory=list, description="Protocols used by this application"
    )
    ports: list[int] = Field(default_factory=list, description="Common ports used")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Country(BaseModel):
    """Country information model."""

    code: str = Field(..., description="ISO country code")
    name: str = Field(..., description="Country name")
    iso_code: str | None = Field(None, description="ISO 3166-1 alpha-2 code")
    iso3_code: str | None = Field(None, description="ISO 3166-1 alpha-3 code")

    # Regulatory information
    regulatory_domain: str | None = Field(None, description="Regulatory domain for wireless")

    model_config = ConfigDict(populate_by_name=True, extra="allow")
