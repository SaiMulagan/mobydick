"""
End-to-end orchestration: free-text survey -> ordered curriculum.

Also handles persistence and caching when a user_id is provided. Same-user
same-survey requests within CACHE_TTL_DAYS short-circuit by returning the
last saved curriculum, skipping all Gemini + BigQuery work.
"""

import json
from datetime import datetime, timedelta
from typing import Optional

import reflex as rx
from sqlmodel import select

from candidates import fetch_candidates
from curriculum import generate_curriculum
from db import Curriculum as CurriculumRow
from db import Progress as ProgressRow
from extract import extract_filters
from schema import Curriculum, CurriculumPick

POOL_SIZE = 25                # cost cap; tunable per cost analysis
CACHE_TTL_DAYS = 7            # same-user same-survey reuses within this window


def _normalize(text: str) -> str:
    """Lowercase + strip + collapse internal whitespace, for cache keying."""
    return " ".join(text.lower().strip().split())


def _try_cache(
    user_id: str, genre: str, time_to_read: str, difficulty: str
) -> Optional[Curriculum]:
    """Return the most recent matching saved curriculum, or None."""
    cutoff = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
    with rx.session() as session:
        row = session.exec(
            select(CurriculumRow)
            .where(CurriculumRow.user_id == user_id)
            .where(CurriculumRow.genre == _normalize(genre))
            .where(CurriculumRow.time_to_read == _normalize(time_to_read))
            .where(CurriculumRow.difficulty == _normalize(difficulty))
            .where(CurriculumRow.created_at >= cutoff)
            .order_by(CurriculumRow.created_at.desc())
        ).first()
        if not row:
            return None
        # Capture attrs while still inside the session — accessing detached
        # instances later triggers a refresh against a closed session.
        picks_json = row.picks_json
        arc = row.overall_arc
        row_id = row.id
    picks = [CurriculumPick(**p) for p in json.loads(picks_json)]
    return Curriculum(picks=picks, overall_arc=arc, db_id=row_id)


def _persist(
    user_id: str,
    genre: str,
    time_to_read: str,
    difficulty: str,
    result: Curriculum,
) -> None:
    """Save the curriculum + one Progress row per pick. Idempotent enough —
    if you submit the same survey again you get a fresh row, but the cache
    above will short-circuit before we hit this on a re-submit."""
    now = datetime.utcnow()
    picks_json = json.dumps([p.model_dump() for p in result.picks])
    with rx.session() as session:
        curr_row = CurriculumRow(
            user_id=user_id,
            genre=_normalize(genre),
            time_to_read=_normalize(time_to_read),
            difficulty=_normalize(difficulty),
            overall_arc=result.overall_arc,
            picks_json=picks_json,
            created_at=now,
        )
        session.add(curr_row)
        session.commit()
        session.refresh(curr_row)  # populate curr_row.id

        # Capture the id while we're still inside the session — accessing
        # detached ORM instances later raises DetachedInstanceError.
        new_id = curr_row.id

        for p in result.picks:
            session.add(
                ProgressRow(
                    user_id=user_id,
                    curriculum_id=new_id,
                    week=p.week,
                    book_id=p.book_id,
                    status="not_started",
                    updated_at=now,
                )
            )
        session.commit()

    # Stamp the saved row's PK on the result so the caller (Reflex State)
    # can wire check-ins without a follow-up query.
    result.db_id = new_id


def generate_for_survey(
    genre: str,
    time_to_read: str,
    difficulty: str,
    already_read_titles: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> Curriculum:
    """End-to-end: 3 free-text fields + optional already-read list -> curriculum.

    If user_id is provided, the result is persisted to the DB and a cache
    lookup is attempted before doing any Gemini/BigQuery work.
    """
    already_read_titles = already_read_titles or []

    # Cache check (only when we have a user identity AND no exclude list —
    # exclude list invalidates the cache because it changes the candidate pool).
    if user_id and not already_read_titles:
        cached = _try_cache(user_id, genre, time_to_read, difficulty)
        if cached:
            return cached

    filters = extract_filters(genre, time_to_read, difficulty)
    if not filters.is_recognized_topic:
        raise ValueError(
            "We couldn't recognize that as a topic. Try something specific "
            "like 'Russian literature' or 'popular astrophysics'."
        )
    rows = fetch_candidates(filters, exclude_titles=already_read_titles)
    pool = rows[:POOL_SIZE]
    if not pool:
        raise ValueError(
            "No matching books were found in the catalog. "
            "Try a broader genre or different keywords."
        )
    result = generate_curriculum(genre, time_to_read, difficulty, pool)

    if user_id:
        _persist(user_id, genre, time_to_read, difficulty, result)

    return result
