"""
SQLModel definitions for the Phase 2 personalization layer.

Reflex wraps SQLModel as `rx.Model`; it adds Alembic-driven migrations.
SQLite is the local backend (configured in rxconfig.py); Cloud SQL when we
deploy. All tables are namespaced under the same DB.
"""

from datetime import datetime
from typing import Optional

import reflex as rx
import sqlmodel
from sqlmodel import Field


class User(rx.Model, table=True):
    """Anonymous identity. id is a UUID stored in a browser cookie."""
    id: str = Field(primary_key=True)
    display_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Curriculum(rx.Model, table=True):
    """One generation. picks_json is a list[dict] serialized; for the demo
    we don't need a normalized picks table, but we'll add one in step 3 if
    progress tracking benefits from it."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    genre: str
    time_to_read: str
    difficulty: str
    overall_arc: str
    picks_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Progress(rx.Model, table=True):
    """Per-pick state and check-in feedback."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    curriculum_id: int = Field(foreign_key="curriculum.id", index=True)
    week: int
    book_id: str
    status: str = "not_started"          # not_started / reading / finished / abandoned
    rating: Optional[int] = None          # 1-5
    difficulty_felt: Optional[str] = None  # too_easy / just_right / too_dense / abandoned
    comment: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ReadBook(rx.Model, table=True):
    """Books the user already read (declared in survey or completed via app)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    book_id: Optional[str] = None
    title: str
    author: Optional[str] = None
    source: str = "pre_existing"  # pre_existing / completed_via_app
    added_at: datetime = Field(default_factory=datetime.utcnow)