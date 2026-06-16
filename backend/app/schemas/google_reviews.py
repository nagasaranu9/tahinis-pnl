import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GoogleReviewConfigResponse(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    place_id: str
    account_name: str | None
    location_name: str | None
    is_active: bool
    last_synced_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class GoogleReviewLocationOverride(BaseModel):
    location_id: uuid.UUID
    account_name: str
    location_name: str


class GoogleReviewResponse(BaseModel):
    id: uuid.UUID
    review_id: str
    author_name: str | None
    rating: int | None
    comment: str | None
    published_at: datetime | None
    reply_comment: str | None
    model_config = ConfigDict(from_attributes=True)


class ReviewsSummaryResponse(BaseModel):
    average_rating: float | None
    total_review_count: int
    five_star: int
    four_star: int
    three_star: int
    two_star: int
    one_star: int
    recent_reviews: list[GoogleReviewResponse]
