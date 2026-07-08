from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class Platform(StrEnum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


class MarketStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLVED = "resolved"


class MarketType(StrEnum):
    BINARY = "binary"
    SUM_TO_ONE = "sum_to_one"
    WINNER_TAKE_ALL = "winner_take_all"
    THRESHOLD_LADDER = "threshold_ladder"


class MarketRecord(BaseModel):
    id: UUID
    platform: Platform
    platform_id: str
    question: str
    outcomes: list[str]
    status: MarketStatus
    resolution: str | None = None
    created_at: datetime
    closes_at: datetime | None = None
    resolved_at: datetime | None = None
    platform_event_id: str | None = None
    platform_event_name: str | None = None
    event_group_id: UUID | None = None
    event_group_name: str | None = None
    category: str | None = None
    tags: list[str] = []
    market_type: MarketType | None = None
    volume: float | None = None
    liquidity: float | None = None
    platform_url: str | None = None


class MarketSummary(BaseModel):
    id: UUID
    question: str
    platform: Platform
    current_prices: dict[str, float] | None = None
    platform_url: str | None = None


class PricePoint(BaseModel):
    timestamp: datetime
    prices: dict[str, float]
    source: str = "poll"


class ScalarPricePoint(BaseModel):
    timestamp: datetime
    probability: float


class MarketHistoryPoint(BaseModel):
    timestamp: datetime
    probability: float | None = None
    provenance: str | None = None


class MarketHistorySeries(BaseModel):
    outcome: str
    points: list[MarketHistoryPoint]


class MarketHistoryResponse(BaseModel):
    market: MarketRecord
    start: datetime
    end: datetime
    interval_minutes: int
    series: list[MarketHistorySeries]
