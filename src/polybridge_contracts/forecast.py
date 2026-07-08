from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from polybridge_contracts.graph import CausalGraphView
from polybridge_contracts.market import MarketRecord, MarketSummary, PricePoint


class EngineType(StrEnum):
    LLM_STANDIN = "llm_standin"
    MATH_ENGINE = "math_engine"
    ORACLE_PORT = "oracle_port"
    LLM_FALLBACK = "llm_fallback"


class ConfidenceInterval(BaseModel):
    lower: float
    upper: float


class ForecastRequest(BaseModel):
    question: str
    include_graph: bool = True


class ForecastResponse(BaseModel):
    request_id: str
    question: str
    probability: float | None = None
    confidence: float
    confidence_interval: ConfidenceInterval | None = None
    reasoning: str
    engine_type: EngineType
    causal_graph: CausalGraphView | None = None
    markets_used: list[MarketSummary]
    distribution: dict[str, float] | None = None
    latency_ms: int
    error: str | None = None
    metadata: dict = {}


class MarketResponse(BaseModel):
    market: MarketRecord
    current_prices: dict[str, float] | None
    price_history: list[PricePoint] = []


class ForecastEvent(BaseModel):
    event_type: str
    data: dict
