"""Search tool implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from polybridge_contracts.search import SearchResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

ALLOWED_DIMENSIONS = ("direct", "upstream", "downstream", "correlated")
ALLOWED_STATUSES = ("active", "closed", "resolved")
AllowedDimension = Literal["direct", "upstream", "downstream", "correlated"]
AllowedStatus = Literal["active", "closed", "resolved"]
DEFAULT_SEARCH_DIMENSIONS = ["direct", "upstream", "downstream", "correlated"]

POLYBRIDGE_SEARCH_TOOL_DESCRIPTION = (
    "Search public prediction markets for markets relevant to a natural-language topic "
    "or question. Use when you need candidate markets, market URLs, outcomes, statuses, "
    "and relevance scores. Do not use for a final probability forecast, market-history "
    "lookup, trading, or private/internal data. Scores are relevance scores, not "
    "probabilities."
)


@dataclass(frozen=True, slots=True)
class SearchToolLimits:
    max_dimensions: int
    max_top_k_per_dimension: int


ANONYMOUS_SEARCH_TOOL_LIMITS = SearchToolLimits(max_dimensions=4, max_top_k_per_dimension=50)
API_KEY_SEARCH_TOOL_LIMITS = SearchToolLimits(max_dimensions=4, max_top_k_per_dimension=100)


def resolve_search_tool_limits(*, api_key_present: bool) -> SearchToolLimits:
    if api_key_present:
        return API_KEY_SEARCH_TOOL_LIMITS
    return ANONYMOUS_SEARCH_TOOL_LIMITS


class SearchResponseShapeError(ValueError):
    """Raised when the backend returns an unexpected Search response shape."""


class SearchToolFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AllowedStatus | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> SearchToolFilters:
        if self.status is None:
            raise ValueError("filters must include status")
        return self


class SearchToolRequest(BaseModel):
    query: str
    dimensions: list[AllowedDimension] = Field(
        default_factory=lambda: list(DEFAULT_SEARCH_DIMENSIONS),
        min_length=1,
    )
    top_k_per_dimension: int = Field(default=5, ge=1)
    filters: SearchToolFilters | None = None

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must be non-empty")
        return normalized

    @model_validator(mode="after")
    def validate_limits(self, info: ValidationInfo) -> SearchToolRequest:
        limits = _resolve_limits_from_context(info.context)

        if len(self.dimensions) > limits.max_dimensions:
            raise ValueError(f"dimensions must contain at most {limits.max_dimensions} items")
        if self.top_k_per_dimension > limits.max_top_k_per_dimension:
            raise ValueError(
                "top_k_per_dimension must be less than or equal to "
                f"{limits.max_top_k_per_dimension}"
            )
        return self

    def to_api_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "query": self.query,
            "dimensions": list(self.dimensions),
            "top_k_per_dimension": self.top_k_per_dimension,
        }
        if self.filters is not None:
            filters_payload = self.filters.model_dump(exclude_none=True)
            if filters_payload:
                payload["filters"] = filters_payload
        return payload


class PublicSearchResult(BaseModel):
    id: str
    platform: str
    question: str
    outcomes: list[str]
    status: AllowedStatus
    platform_url: str | None = None
    score: float
    dimension: str | None = None


class PublicSearchResponse(BaseModel):
    request_id: str
    query: str
    results: dict[str, list[PublicSearchResult]]
    total_markets: int
    latency_ms: int | float


SearchAPIResponse = SearchResponse | PublicSearchResponse


class CompactSearchResult(BaseModel):
    dimension: str
    rank: int
    market_id: str
    platform: str
    question: str
    outcomes: list[str]
    status: AllowedStatus
    platform_url: str | None = None
    score: float
    warnings: list[str] = Field(default_factory=list)


class CompactSearchResponse(BaseModel):
    request_id: str
    query: str
    total_markets: int
    dimensions_returned: list[str]
    results: list[CompactSearchResult]
    warnings: list[str] = Field(default_factory=list)


def parse_search_response_payload(payload: Any) -> SearchAPIResponse:
    try:
        return PublicSearchResponse.model_validate(payload)
    except ValidationError:
        try:
            return SearchResponse.model_validate(payload)
        except ValidationError as exc:
            raise SearchResponseShapeError(
                "PolyBridge Search API returned an unexpected response shape"
            ) from exc


def format_search_response(response: SearchAPIResponse) -> CompactSearchResponse:
    if isinstance(response, PublicSearchResponse):
        return _format_public_search_response(response)
    return _format_internal_search_response(response)


def _format_public_search_response(response: PublicSearchResponse) -> CompactSearchResponse:
    compact_results: list[CompactSearchResult] = []
    dimensions_returned = list(response.results.keys())

    for dimension in dimensions_returned:
        for rank, result in enumerate(response.results[dimension], start=1):
            compact_results.append(
                CompactSearchResult(
                    dimension=result.dimension or dimension,
                    rank=rank,
                    market_id=result.id,
                    platform=result.platform,
                    question=result.question,
                    outcomes=list(result.outcomes),
                    status=result.status,
                    platform_url=result.platform_url,
                    score=result.score,
                    warnings=_build_result_warnings(result.platform_url),
                )
            )

    return CompactSearchResponse(
        request_id=response.request_id,
        query=response.query,
        total_markets=response.total_markets,
        dimensions_returned=dimensions_returned,
        results=compact_results,
    )


def _format_internal_search_response(response: SearchResponse) -> CompactSearchResponse:
    compact_results: list[CompactSearchResult] = []
    dimensions_returned = list(response.results.keys())

    for dimension in dimensions_returned:
        for rank, result in enumerate(response.results[dimension], start=1):
            compact_results.append(
                CompactSearchResult(
                    dimension=result.dimension or dimension,
                    rank=rank,
                    market_id=str(result.market.id),
                    platform=result.market.platform.value,
                    question=result.market.question,
                    outcomes=list(result.market.outcomes),
                    status=result.market.status.value,
                    platform_url=result.market.platform_url,
                    score=result.score,
                    warnings=_build_result_warnings(result.market.platform_url),
                )
            )

    return CompactSearchResponse(
        request_id=response.request_id,
        query=response.query,
        total_markets=response.total_markets,
        dimensions_returned=dimensions_returned,
        results=compact_results,
    )


def _build_result_warnings(platform_url: str | None) -> list[str]:
    warnings: list[str] = []
    if platform_url is None:
        warnings.append("Market URL was not included in the Search API response.")
    return warnings


def _resolve_limits_from_context(context: Any) -> SearchToolLimits:
    if isinstance(context, dict):
        maybe_limits = context.get("search_limits")
        if isinstance(maybe_limits, SearchToolLimits):
            return maybe_limits
    return ANONYMOUS_SEARCH_TOOL_LIMITS
