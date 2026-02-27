"""Pydantic schemas for /memory endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MemoryTypeEnum = Literal["preference", "session", "growth", "creative"]


class MemoryEntryResponse(BaseModel):
    """Serialized MemoryEntry for API responses."""

    memory_id: str
    memory_type: MemoryTypeEnum
    content: str
    created_at: str
    updated_at: str
    pinned: bool
    tags: list[str]
    source: str


class CreateMemoryRequest(BaseModel):
    memory_type: MemoryTypeEnum
    content: str = Field(..., min_length=1, max_length=2000)
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False


class UpdateMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class MemoryListResponse(BaseModel):
    entries: list[MemoryEntryResponse]
    total: int


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    memory_types: list[MemoryTypeEnum] | None = None
