from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from polybridge_contracts.market import MarketSummary, PricePoint, ScalarPricePoint
from polybridge_contracts.search import SearchResult

# --- Internal types ---


class GraphInput(BaseModel):
    question: str
    search_results: dict[str, list[SearchResult]]


class Edge(BaseModel):
    source: str
    target: str
    edge_type: str
    role: str | None = None
    polarity: str = "unknown"
    confidence: str = "abstain"
    hard_constraint: bool = False
    causal_distance: int | None = None
    supports_intervention: bool = False
    properties: dict = {}


class LatentMetadata(BaseModel):
    family_id: str | None = None
    family_type: str | None = None
    family_rank: int | None = None
    family_members: list[str] | None = None
    target_outcome: str | None = None
    properties: dict = {}


class EventMetadata(BaseModel):
    family_id: str | None = None
    family_type: str | None = None
    event_anchor: str | None = None
    representative_market_id: str | None = None
    properties: dict = {}


class GraphOutput(BaseModel):
    target_event_id: str | None = None
    event_definitions: dict[str, list[str]] = {}
    event_histories: dict[str, list[ScalarPricePoint]] = {}
    event_metadata: dict[str, EventMetadata] = {}
    target_latent_id: str | None = None
    latent_definitions: dict[str, list[str]] = {}
    edges: list[Edge]
    latent_histories: dict[str, list[ScalarPricePoint]] = {}
    market_prices: dict[str, list[PricePoint]] | None = None
    market_questions: dict[str, str]
    latent_metadata: dict[str, LatentMetadata] = {}
    evidence: dict[str, float] | None = None
    evidence_full: dict[str, dict[str, float]] | None = None
    queries: list | None = None

    @model_validator(mode="after")
    def _sync_event_and_latent_views(self) -> GraphOutput:
        if self.event_definitions and not self.latent_definitions:
            self.latent_definitions = dict(self.event_definitions)
        if self.latent_definitions and not self.event_definitions:
            self.event_definitions = dict(self.latent_definitions)

        if self.event_histories and not self.latent_histories:
            self.latent_histories = dict(self.event_histories)
        if self.latent_histories and not self.event_histories:
            self.event_histories = dict(self.latent_histories)

        if self.event_metadata and not self.latent_metadata:
            self.latent_metadata = {
                event_id: LatentMetadata(
                    family_id=metadata.family_id,
                    family_type=metadata.family_type,
                    target_outcome=None,
                    properties=dict(metadata.properties),
                )
                for event_id, metadata in self.event_metadata.items()
            }
        if self.latent_metadata and not self.event_metadata:
            self.event_metadata = {
                latent_id: EventMetadata(
                    family_id=metadata.family_id,
                    family_type=metadata.family_type,
                    representative_market_id=(
                        metadata.properties.get("representative_market_id")
                        if isinstance(metadata.properties, dict)
                        else None
                    ),
                    properties=dict(metadata.properties),
                )
                for latent_id, metadata in self.latent_metadata.items()
            }

        if self.target_event_id is None:
            self.target_event_id = self.target_latent_id
        if self.target_latent_id is None:
            self.target_latent_id = self.target_event_id
        return self


class LatentTrace(BaseModel):
    latent_id: str
    label: str
    market_ids: list[str]
    source: str
    grouping_rationale: str | None = None
    family_id: str | None = None
    family_type: str | None = None
    target_outcome: str | None = None
    search_dimensions: list[str] = Field(default_factory=list)
    max_search_score: float = 0.0
    direct_score: float = 0.0
    representative_market_id: str | None = None
    markets_with_history: int = 0
    coverage_points: int = 0
    coverage_status: str | None = None
    purity_score: float | None = None
    purity_status: str | None = None
    purity_warnings: list[str] = Field(default_factory=list)


class EventTrace(BaseModel):
    event_id: str
    label: str
    market_ids: list[str]
    source: str
    grouping_rationale: str | None = None
    family_id: str | None = None
    family_type: str | None = None
    event_anchor: str | None = None
    search_dimensions: list[str] = Field(default_factory=list)
    max_search_score: float = 0.0
    direct_score: float = 0.0
    representative_market_id: str | None = None
    markets_with_history: int = 0
    coverage_points: int = 0
    coverage_status: str | None = None
    purity_score: float | None = None
    purity_status: str | None = None
    purity_warnings: list[str] = Field(default_factory=list)


class TargetSelectionCandidateTrace(BaseModel):
    latent_id: str
    market_ids: list[str] = Field(default_factory=list)
    max_direct_score: float = 0.0
    max_search_score: float = 0.0
    selected: bool = False


class TargetSelectionTrace(BaseModel):
    selected_latent_id: str | None = None
    rationale: str | None = None
    candidates: list[TargetSelectionCandidateTrace] = Field(default_factory=list)


class BuildGraphTrace(BaseModel):
    question: str
    unique_market_count: int
    events: list[EventTrace] = Field(default_factory=list)
    latents: list[LatentTrace] = Field(default_factory=list)
    edge_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    llm_provider: str | None = None
    representative_markets: dict[str, str] = Field(default_factory=dict)
    coverage: dict[str, int] = Field(default_factory=dict)
    semantic_candidate_ids: list[str] = Field(default_factory=list)
    semantic_candidate_markets: list[dict] = Field(default_factory=list)
    target_selection: TargetSelectionTrace | None = None

    @model_validator(mode="after")
    def _sync_event_and_latent_traces(self) -> BuildGraphTrace:
        if self.events and not self.latents:
            self.latents = [
                LatentTrace(
                    latent_id=item.event_id,
                    label=item.label,
                    market_ids=list(item.market_ids),
                    source=item.source,
                    grouping_rationale=item.grouping_rationale,
                    family_id=item.family_id,
                    family_type=item.family_type,
                    target_outcome=None,
                    search_dimensions=list(item.search_dimensions),
                    max_search_score=item.max_search_score,
                    direct_score=item.direct_score,
                    representative_market_id=item.representative_market_id,
                    markets_with_history=item.markets_with_history,
                    coverage_points=item.coverage_points,
                    coverage_status=item.coverage_status,
                    purity_score=item.purity_score,
                    purity_status=item.purity_status,
                    purity_warnings=list(item.purity_warnings),
                )
                for item in self.events
            ]
        if self.latents and not self.events:
            self.events = [
                EventTrace(
                    event_id=item.latent_id,
                    label=item.label,
                    market_ids=list(item.market_ids),
                    source=item.source,
                    grouping_rationale=item.grouping_rationale,
                    family_id=item.family_id,
                    family_type=item.family_type,
                    event_anchor=item.family_id,
                    search_dimensions=list(item.search_dimensions),
                    max_search_score=item.max_search_score,
                    direct_score=item.direct_score,
                    representative_market_id=item.representative_market_id,
                    markets_with_history=item.markets_with_history,
                    coverage_points=item.coverage_points,
                    coverage_status=item.coverage_status,
                    purity_score=item.purity_score,
                    purity_status=item.purity_status,
                    purity_warnings=list(item.purity_warnings),
                )
                for item in self.latents
            ]
        return self


GraphBuildJobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]


class GraphBuildJobCreateRequest(BaseModel):
    question: str
    search_results: dict[str, list[SearchResult]]


class GraphBuildJobCreateResponse(BaseModel):
    job_id: UUID
    status: GraphBuildJobStatus
    created_at: datetime
    pusher_key: str | None = None
    pusher_cluster: str | None = None
    pusher_channel: str | None = None


class GraphBuildJobStatusResponse(BaseModel):
    job_id: UUID
    status: GraphBuildJobStatus
    progress_stage: str | None = None
    progress_detail: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    graph: GraphOutput | None = None
    trace: BuildGraphTrace | None = None


# --- External types ---


class GraphNode(BaseModel):
    id: str
    label: str
    markets: list[MarketSummary]
    current_probability: float | None


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    strength: float | None
    description: str | None


class CausalGraphView(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
