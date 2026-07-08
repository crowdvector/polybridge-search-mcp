from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from polybridge_contracts.market import MarketRecord


class SearchResult(BaseModel):
    market: MarketRecord
    score: float
    dimension: str
    tags: dict = {}
    linked_market_ids: list[UUID] = []


class SearchRequest(BaseModel):
    query: str
    case_question: str | None = None
    dimensions: list[str] = ["direct", "upstream", "downstream", "correlated"]
    top_k_per_dimension: int = 20
    filters: dict | None = None
    strategy_override: str | None = None


class SearchResponse(BaseModel):
    request_id: str
    query: str
    results: dict[str, list[SearchResult]]
    total_markets: int
    latency_ms: int
