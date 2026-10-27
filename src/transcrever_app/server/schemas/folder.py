"""Folder API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FolderResponse(BaseModel):
    """Public logical folder representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_id: str | None
    name: str
    is_pinned: bool
    position: int
    created_at: datetime
    updated_at: datetime


class FolderCreate(BaseModel):
    """Folder creation input."""

    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None


class FolderPatch(BaseModel):
    """Editable folder metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    is_pinned: bool | None = None
    position: int | None = Field(default=None, ge=0)


class FolderMove(BaseModel):
    """Folder parent change input."""

    parent_id: str | None = None


class FolderTreeResponse(FolderResponse):
    """Folder representation enriched with its full logical path."""

    path: str
