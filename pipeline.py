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
from schema import Curriculum, CurriculumPick, PageRange

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


def _difficulty_bias_for(user_id: str) -> Optional[str]:
    """Inspect the user's last 10 check-ins. Return 'easier' / 'harder' /
    None depending on which direction recent difficulty_felt values lean."""
    if not user_id:
        return None
    with rx.session() as session:
        rows = session.exec(
            select(ProgressRow.difficulty_felt)
            .where(ProgressRow.user_id == user_id)
            .where(ProgressRow.difficulty_felt.is_not(None))
            .order_by(ProgressRow.updated_at.desc())
            .limit(10)
        ).all()
    counts = {"too_easy": 0, "just_right": 0, "too_dense": 0}
    for r in rows:
        if r in counts:
            counts[r] += 1
    total = sum(counts.values())
    if total < 2:
        return None
    if counts["too_dense"] / total >= 0.4:
        return "easier"
    if counts["too_easy"] / total >= 0.4:
        return "harder"
    return None


def _hint_text(bias: Optional[str]) -> str:
    """Prompt addendum for extract.py — biases Gemini's extraction."""
    if bias == "easier":
        return (
            "USER PROFILE NOTE: This reader has marked multiple recent books "
            "as 'too dense'. Bias the extracted `difficulty` one notch easier "
            "than the literal request (high -> medium, medium -> low)."
        )
    if bias == "harder":
        return (
            "USER PROFILE NOTE: This reader has marked multiple recent books "
            "as 'too easy'. Bias the extracted `difficulty` one notch harder "
            "than the literal request (low -> medium, medium -> high)."
        )
    return ""


# Maps for the deterministic Python-side override that follows extraction.
_EASIER = {"high": "medium", "medium": "low", "low": "low"}
_HARDER = {"low": "medium", "medium": "high", "high": "high"}


def _apply_bias(filters, bias: Optional[str]):
    """Deterministically enforce the bias after extraction.

    Gemini's hint-following is best-effort; this guarantees the change
    actually lands AND tightens page_range when 'easier', which is what
    makes the difference visible in the candidate pool (the SQL filters
    on page_range — long classics get excluded outright).
    """
    if bias is None:
        return filters
    if bias == "easier":
        filters.difficulty = _EASIER[filters.difficulty]
        # Trim long-book ceiling by ~30%, floor at min+50 to stay valid.
        new_max = max(int(filters.page_range.max * 0.7),
                      filters.page_range.min + 50)
        filters.page_range = PageRange(
            min=filters.page_range.min, max=new_max
        )
    elif bias == "harder":
        filters.difficulty = _HARDER[filters.difficulty]
    return filters


def _titles_from_past_progress(user_id: str) -> list[str]:
    """Return titles of books this user has already engaged with across all
    past curricula — any status other than `not_started`. Used to auto-
    exclude them from new candidate pools so a finished/abandoned/in-progress
    book never resurfaces in a new curriculum.

    Goes through each Curriculum row's picks_json (where titles live) and
    cross-references it with the Progress rows for that curriculum.
    """
    with rx.session() as session:
        curricula = session.exec(
            select(CurriculumRow).where(CurriculumRow.user_id == user_id)
        ).all()
        if not curricula:
            return []

        # (curriculum_id, picks_json) pairs, materialized inside the session.
        snapshots = [(c.id, c.picks_json) for c in curricula]

        excluded: list[str] = []
        for curr_id, picks_json in snapshots:
            picks_by_id = {
                p["book_id"]: p["title"] for p in json.loads(picks_json)
            }
            rows = session.exec(
                select(ProgressRow)
                .where(ProgressRow.curriculum_id == curr_id)
                .where(ProgressRow.status != "not_started")
            ).all()
            for r in rows:
                title = picks_by_id.get(r.book_id)
                if title:
                    excluded.append(title)
    return excluded


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

    Books the user has engaged with in any past curriculum (status != not_started)
    are auto-excluded from the new candidate pool — closes the feedback loop
    so finished/abandoned/in-progress books don't resurface.
    """
    survey_excludes = list(already_read_titles or [])

    # Pull auto-excludes from progress before the cache check, since the
    # presence of past engagement changes what a "valid" cached result is.
    auto_excludes = _titles_from_past_progress(user_id) if user_id else []
    full_exclude_list = survey_excludes + auto_excludes

    # Cache lookup is only safe when nothing needs to be excluded — otherwise
    # the candidate pool can shift between submissions of the same survey.
    if user_id and not full_exclude_list:
        cached = _try_cache(user_id, genre, time_to_read, difficulty)
        if cached:
            return cached

    # Personalized difficulty bias from past check-ins. Two layers:
    #   1) Soft nudge in the extraction prompt (Gemini may follow it).
    #   2) Deterministic Python override after extraction — guarantees the
    #      change lands AND tightens page_range, which is what actually
    #      shifts the candidate pool at the SQL layer.
    bias = _difficulty_bias_for(user_id) if user_id else None
    filters = extract_filters(genre, time_to_read, difficulty, _hint_text(bias))
    if not filters.is_recognized_topic:
        raise ValueError(
            "We couldn't recognize that as a topic. Try something specific "
            "like 'Russian literature' or 'popular astrophysics'."
        )

    # Enforce the bias deterministically — guarantees the page_range tightens
    # so the SQL filter actually excludes the long classics from the pool,
    # and the curation prompt below sees the adjusted difficulty.
    filters = _apply_bias(filters, bias)

    rows = fetch_candidates(filters, exclude_titles=full_exclude_list)
    pool = rows[:POOL_SIZE]
    if not pool:
        raise ValueError(
            "No matching books were found in the catalog. "
            "Try a broader genre or different keywords."
        )
    # Pass the (possibly biased) extracted difficulty, not the raw user input
    # — this is what propagates the calibration into the curation step.
    result = generate_curriculum(genre, time_to_read, filters.difficulty, pool)

    if user_id:
        _persist(user_id, genre, time_to_read, difficulty, result)

    return result
