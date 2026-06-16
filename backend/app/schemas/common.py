from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    data: T | None = None
    errors: list[dict] | None = None


class PaginatedMeta(BaseModel):
    page: int
    limit: int
    total: int


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: PaginatedMeta
    errors: list[dict] | None = None
