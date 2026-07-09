"""RVOL tool implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

RVOL_API_KEY_REQUIRED_MESSAGE = (
    "RVOL requires a PolyBridge API key with rvol:read. Set POLYBRIDGE_API_KEY in "
    "Claude Desktop or generate an approved key in the Developer Console."
)

POLYBRIDGE_RVOL_MODELS_TOOL_DESCRIPTION = (
    "Read-only RVOL models lookup. Requires POLYBRIDGE_API_KEY with rvol:read."
)
POLYBRIDGE_RVOL_ASSETS_TOOL_DESCRIPTION = (
    "Read-only RVOL assets lookup. Requires POLYBRIDGE_API_KEY with rvol:read."
)
POLYBRIDGE_RVOL_LATEST_TOOL_DESCRIPTION = (
    "Read-only latest RVOL forecasts lookup. Requires POLYBRIDGE_API_KEY with rvol:read."
)
POLYBRIDGE_RVOL_HISTORY_TOOL_DESCRIPTION = (
    "Read-only RVOL forecast history lookup. Requires POLYBRIDGE_API_KEY with rvol:read."
)
POLYBRIDGE_RVOL_ACTUALS_TOOL_DESCRIPTION = (
    "Read-only RVOL actuals lookup. Requires POLYBRIDGE_API_KEY with rvol:read."
)
POLYBRIDGE_RVOL_FEATURES_LATEST_TOOL_DESCRIPTION = (
    "Read-only latest RVOL feature metadata lookup. Requires POLYBRIDGE_API_KEY with "
    "rvol:read."
)

RvolAPIResponse = list[dict[str, Any]]

PUBLIC_RVOL_FIELDS = frozenset(
    {
        "model_id",
        "model_version",
        "aliases",
        "trained_through",
        "updated_at",
        "asset",
        "display_name",
        "target_family",
        "default_horizon",
        "active",
        "horizon",
        "as_of",
        "target_start_at",
        "target_end_at",
        "prediction",
        "prediction_value",
        "forecast_variance",
        "forecast_volatility",
        "annualized_volatility",
        "unit",
        "actual",
        "actual_value",
        "realized_variance",
        "realized_volatility",
        "feature_set_id",
        "feature_families",
    }
)


class RvolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_query_params(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)


class RvolModelsRequest(RvolRequest):
    model_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class RvolAssetsRequest(RvolRequest):
    include_inactive: bool = False
    limit: int = Field(default=500, ge=1, le=1000)


class RvolLatestRequest(RvolRequest):
    model: str | None = None
    model_version: str | None = None
    asset: str | None = None
    horizon: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class RvolHistoryRequest(RvolRequest):
    model: str | None = None
    model_version: str | None = None
    asset: str | None = None
    horizon: str | None = None
    start: str | None = None
    end: str | None = None
    limit: int = Field(default=1000, ge=1, le=10000)

    @field_validator("start", "end")
    @classmethod
    def validate_iso_datetime(cls, value: str | None) -> str | None:
        return _validate_optional_iso_datetime(value)


class RvolActualsRequest(RvolRequest):
    asset: str | None = None
    horizon: str | None = None
    start: str | None = None
    end: str | None = None
    limit: int = Field(default=1000, ge=1, le=10000)

    @field_validator("start", "end")
    @classmethod
    def validate_iso_datetime(cls, value: str | None) -> str | None:
        return _validate_optional_iso_datetime(value)


class RvolFeaturesLatestRequest(RvolRequest):
    asset: str | None = None
    horizon: str | None = None
    feature_set_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


def filter_public_rvol_payload(payload: Any) -> RvolAPIResponse:
    if not isinstance(payload, list):
        raise ValueError("PolyBridge RVOL API returned an unexpected response shape")
    return [_filter_public_rvol_item(item) for item in payload if isinstance(item, dict)]


def _filter_public_rvol_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _filter_public_rvol_value(value)
        for key, value in item.items()
        if key in PUBLIC_RVOL_FIELDS
    }


def _filter_public_rvol_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _filter_public_rvol_item(value)
    if isinstance(value, list):
        return [
            _filter_public_rvol_value(item)
            for item in value
            if not isinstance(item, dict) or any(key in PUBLIC_RVOL_FIELDS for key in item)
        ]
    return value


def _validate_optional_iso_datetime(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError("must be a non-empty ISO date-time string")
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("must be an ISO date-time string") from exc
    return normalized
