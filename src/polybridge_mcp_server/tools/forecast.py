"""Forecast tool implementation."""

from __future__ import annotations

from typing import Any

from polybridge_contracts.forecast import EngineType, ForecastResponse
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

PUBLIC_FORECAST_MAX_QUESTION_CHARS = 500

POLYBRIDGE_FORECAST_TOOL_DESCRIPTION = (
    "Generate a read-only probability forecast for a clearly stated future event by "
    "searching relevant prediction markets and synthesizing evidence. Use when the user "
    "asks for a probability, outlook, or forecast; use polybridge_search when they only "
    "need market discovery. Does not place trades, provide financial advice, or access "
    "private/internal data."
)


class ForecastResponseShapeError(ValueError):
    """Raised when the backend returns an unexpected Forecast response shape."""


class ForecastToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    include_graph: bool = True

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must be non-empty")
        if len(normalized) > PUBLIC_FORECAST_MAX_QUESTION_CHARS:
            raise ValueError("question must be 500 characters or fewer")
        return normalized

    def to_api_payload(self) -> dict[str, object]:
        return {
            "question": self.question,
            "include_graph": self.include_graph,
        }


def parse_forecast_response_payload(payload: Any) -> ForecastResponse:
    try:
        return ForecastResponse.model_validate(payload)
    except ValidationError as exc:
        normalized_payload = _normalize_oracle_port_engine_type(payload)
        if normalized_payload is not None:
            try:
                return ForecastResponse.model_validate(normalized_payload)
            except ValidationError:
                pass
        raise ForecastResponseShapeError(
            "PolyBridge Forecast API returned an unexpected response shape"
        ) from exc


def _normalize_oracle_port_engine_type(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    engine_type = payload.get("engine_type")
    if not isinstance(engine_type, str):
        return None
    if engine_type in {member.value for member in EngineType}:
        return None

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or "oracle_port" not in metadata:
        return None

    normalized_payload = dict(payload)
    normalized_payload["engine_type"] = EngineType.ORACLE_PORT.value
    return normalized_payload
