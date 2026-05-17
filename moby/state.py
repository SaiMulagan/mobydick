import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import TypedDict

import reflex as rx

from sqlmodel import select

from db import Curriculum as CurriculumRow
from db import Progress, ReadBook, User
from pipeline import generate_for_survey


class ProgressSummary(TypedDict):
    total: int
    finished: int
    reading: int
    abandoned: int
    not_started: int


class DashboardPick(TypedDict):
    book_id: str
    title: str
    author: str
    week: int
    reason: str
    status: str
    rating: int
    difficulty_felt: str
    comment: str


class DashboardCurriculum(TypedDict):
    id: int
    genre: str
    time_to_read: str
    difficulty: str
    overall_arc: str
    created_at: str
    picks: list[DashboardPick]
    summary: ProgressSummary


class State(rx.State):
    # Anonymous identity — auto-syncs with the browser cookie. Empty on first
    # visit; hydrate_user fills it in and creates the matching User row.
    user_id: str = rx.Cookie("")

    # Form inputs
    genre: str = ""
    time_to_read: str = ""
    difficulty: str = ""
    # Free-text list of books the user has already read, one per line.
    # Parsed on submit, persisted to ReadBook, and excluded from the pool.
    already_read: str = ""

    # Result fields (flat — easier for Reflex to serialize than a nested model)
    overall_arc: str = ""
    # Each pick now carries progress-tracking fields too:
    #   {"week", "title", "author", "book_id", "reason",
    #    "status", "rating", "difficulty_felt", "comment"}
    picks: list[dict] = []
    # PK of the active Curriculum row, or 0 if no curriculum is loaded.
    curriculum_id: int = 0

    # Dashboard data: list of past curricula with their progress summaries.
    # Typed so rx.foreach can introspect nested keys like
    # c["summary"]["finished"] in templates.
    dashboard_curricula: list[DashboardCurriculum] = []
    # Header stat counts. All derived from progress rows in one pass.
    dashboard_total_finished: int = 0
    dashboard_total_picks: int = 0
    dashboard_total_reading: int = 0
    dashboard_finished_this_week: int = 0

    # UI status
    is_loading: bool = False
    error: str = ""

    @rx.event
    def set_genre(self, value: str):
        self.genre = value

    @rx.event
    def set_time_to_read(self, value: str):
        self.time_to_read = value

    @rx.event
    def set_difficulty(self, value: str):
        self.difficulty = value

    @rx.event
    def set_already_read(self, value: str):
        self.already_read = value

    @rx.event(background=True)
    async def submit(self):
        async with self:
            if not (self.genre.strip() and self.time_to_read.strip() and self.difficulty.strip()):
                self.error = "Please fill in all three fields."
                return
            self.is_loading = True
            self.error = ""
            self.overall_arc = ""
            self.picks = []
            genre = self.genre
            time_to_read = self.time_to_read
            difficulty = self.difficulty
            user_id = self.user_id
            # Parse one-per-line, drop blanks and stray whitespace.
            already_read_titles = [
                line.strip() for line in self.already_read.splitlines() if line.strip()
            ]

        # Persist the user's already-read list (idempotent enough — duplicates
        # across submissions are tolerated; we'll dedup at query time).
        if already_read_titles:
            with rx.session() as session:
                for title in already_read_titles:
                    session.add(
                        ReadBook(
                            user_id=user_id,
                            title=title,
                            source="pre_existing",
                            added_at=datetime.utcnow(),
                        )
                    )
                session.commit()

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_for_survey,
                    genre, time_to_read, difficulty,
                    already_read_titles,
                    user_id,
                ),
                timeout=60.0,
            )
            # Hydrate picks with their Progress rows so the UI can render
            # check-in controls without a separate fetch. Done outside the
            # state-lock since it does I/O.
            picks_with_progress = _attach_progress(result, user_id)

            async with self:
                self.overall_arc = result.overall_arc
                self.picks = picks_with_progress
                self.curriculum_id = result.db_id or 0
        except ValueError as e:
            async with self:
                self.error = f"Couldn't build a curriculum: {e}"
        except Exception as e:
            async with self:
                self.error = f"Unexpected error ({type(e).__name__}): {e}"
        finally:
            async with self:
                self.is_loading = False

    @rx.event
    def reset_form(self):
        self.genre = ""
        self.time_to_read = ""
        self.difficulty = ""
        self.already_read = ""
        self.overall_arc = ""
        self.picks = []
        self.curriculum_id = 0
        self.error = ""

    @rx.event
    def hydrate_user(self):
        """Fired on page mount. Assigns an anonymous user_id (UUID) and
        creates the matching User row on first visit. Idempotent: no-op
        once the cookie is set."""
        if self.user_id:
            return
        new_id = str(uuid.uuid4())
        with rx.session() as session:
            session.add(User(id=new_id, created_at=datetime.utcnow()))
            session.commit()
        self.user_id = new_id

    @rx.event
    def set_pick_status(self, curriculum_id: int, book_id: str, new_status: str):
        """Update status + lifecycle timestamps for a pick.

        Accepts curriculum_id explicitly so this works from both the
        generation page (one active curriculum) and the dashboard
        (multiple curricula visible at once)."""
        if not curriculum_id:
            return
        now = datetime.utcnow()
        with rx.session() as session:
            row = session.exec(
                select(Progress)
                .where(Progress.curriculum_id == curriculum_id)
                .where(Progress.book_id == book_id)
            ).first()
            if row is None:
                return
            row.status = new_status
            row.updated_at = now
            if new_status == "reading" and row.started_at is None:
                row.started_at = now
            if new_status == "finished":
                row.finished_at = now
            session.add(row)
            session.commit()
        self._propagate_pick_change(curriculum_id, book_id, status=new_status)
        # Status changes affect the summary counts on the dashboard, so
        # reload them (cheap — single user, local SQLite).
        if self.dashboard_curricula:
            self._load_dashboard_data()

    @rx.event
    def set_pick_rating(self, curriculum_id: int, book_id: str, value: str):
        """Update the 1-5 star rating. value comes from rx.select as a
        string ("0" through "5"); 0 / empty maps to NULL in DB."""
        if not curriculum_id:
            return
        try:
            rating_int = int(value) if value else 0
        except ValueError:
            rating_int = 0

        self._patch_progress(curriculum_id, book_id, rating=rating_int or None)
        self._propagate_pick_change(curriculum_id, book_id, rating=rating_int)

    @rx.event
    def set_pick_difficulty_felt(self, curriculum_id: int, book_id: str, value: str):
        """Update the post-read difficulty assessment."""
        if not curriculum_id:
            return
        # rx.select returns "" when cleared; treat as NULL.
        normalized = value if value else None
        self._patch_progress(curriculum_id, book_id, difficulty_felt=normalized)
        self._propagate_pick_change(curriculum_id, book_id, difficulty_felt=value)

    @rx.event
    def update_pick_comment_draft(self, curriculum_id: int, book_id: str, value: str):
        """Update the in-memory comment as the user types. No DB write —
        keeps the textarea responsive without per-keystroke round-trips."""
        self._propagate_pick_change(curriculum_id, book_id, comment=value)

    @rx.event
    def commit_pick_comment(self, curriculum_id: int, book_id: str, value: str):
        """Persist the comment to DB. Fires on blur (focus leaves textarea)."""
        if not curriculum_id:
            return
        self._patch_progress(curriculum_id, book_id, comment=(value or None))

    def _propagate_pick_change(self, curriculum_id: int, book_id: str, **fields) -> None:
        """Reflect a per-pick change in both State.picks (if this is the
        active curriculum) and State.dashboard_curricula (if it's listed)."""
        if self.curriculum_id == curriculum_id:
            self.picks = [
                {**p, **fields} if p["book_id"] == book_id else p
                for p in self.picks
            ]
        # Update the matching pick inside dashboard_curricula too.
        if self.dashboard_curricula:
            self.dashboard_curricula = [
                {
                    **c,
                    "picks": [
                        {**p, **fields} if p["book_id"] == book_id else p
                        for p in c["picks"]
                    ],
                } if c["id"] == curriculum_id else c
                for c in self.dashboard_curricula
            ]

    def _patch_progress(self, curriculum_id: int, book_id: str, **fields) -> None:
        """Internal helper: mutate one or more fields on the Progress row
        for (curriculum_id, book_id). Always bumps updated_at."""
        with rx.session() as session:
            row = session.exec(
                select(Progress)
                .where(Progress.curriculum_id == curriculum_id)
                .where(Progress.book_id == book_id)
            ).first()
            if row is None:
                return
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = datetime.utcnow()
            session.add(row)
            session.commit()

    @rx.event
    def load_dashboard(self):
        """Public event handler — wraps the actual loader so other handlers
        can refresh dashboard state without re-decorating."""
        self._load_dashboard_data()

    @rx.event
    def more_like_this(self, curriculum_id: int, book_id: str):
        """Pre-fill the survey from a finished pick and navigate back to the
        generation page. The auto-exclude logic in pipeline.py will keep the
        seed book itself out of the new pool, and _difficulty_bias_for will
        adjust difficulty if past check-ins warrant it."""
        seed_pick = None
        seed_curriculum = None
        for c in self.dashboard_curricula:
            if c["id"] == curriculum_id:
                seed_curriculum = c
                for p in c["picks"]:
                    if p["book_id"] == book_id:
                        seed_pick = p
                        break
                break
        if seed_pick is None or seed_curriculum is None:
            return

        # Goodreads shelves index on topics (russian-literature, magical-
        # realism), not author names — so a bare "Leo Tolstoy" keyword
        # matches almost nothing and the SQL falls back on broader signals
        # like the Reddit tiebreaker, which surfaces megahits like 1984 and
        # Frankenstein. Combining the original topic with the author gives
        # the extractor both a strong topical anchor AND an author bias.
        seed_topic = seed_curriculum["genre"]
        seed_author = seed_pick["author"]
        self.genre        = f"{seed_topic} like {seed_author}"
        self.time_to_read = seed_curriculum["time_to_read"] or "evening read"
        self.difficulty   = seed_curriculum["difficulty"] or "moderate"
        self.already_read = ""
        self.overall_arc  = ""
        self.picks        = []
        self.curriculum_id = 0
        self.error        = ""

        return rx.redirect("/")

    def _load_dashboard_data(self):
        """Populate dashboard_curricula + the four header stat counts.
        Called on /dashboard mount and after any status change (since
        the summary counts depend on per-pick statuses)."""
        if not self.user_id:
            self.dashboard_curricula = []
            self.dashboard_total_finished = 0
            self.dashboard_total_picks = 0
            self.dashboard_total_reading = 0
            self.dashboard_finished_this_week = 0
            return

        one_week_ago = datetime.utcnow() - timedelta(days=7)

        with rx.session() as session:
            curricula = session.exec(
                select(CurriculumRow)
                .where(CurriculumRow.user_id == self.user_id)
                .order_by(CurriculumRow.created_at.desc())
            ).all()

            built: list[dict] = []
            total_finished = 0
            total_reading = 0
            total_picks = 0
            finished_this_week = 0
            for c in curricula:
                progress_rows = session.exec(
                    select(Progress).where(Progress.curriculum_id == c.id)
                ).all()
                statuses = [pr.status for pr in progress_rows]
                summary = {
                    "total":       len(statuses),
                    "finished":    statuses.count("finished"),
                    "reading":     statuses.count("reading"),
                    "abandoned":   statuses.count("abandoned"),
                    "not_started": statuses.count("not_started"),
                }
                total_finished     += summary["finished"]
                total_reading      += summary["reading"]
                total_picks        += summary["total"]
                # Recent-finish count for the "this week" momentum stat.
                finished_this_week += sum(
                    1 for pr in progress_rows
                    if pr.status == "finished"
                    and pr.finished_at is not None
                    and pr.finished_at >= one_week_ago
                )

                # Hydrate the saved picks JSON with the latest progress.
                by_book = {pr.book_id: pr for pr in progress_rows}
                picks = json.loads(c.picks_json)
                for p in picks:
                    pr = by_book.get(p["book_id"])
                    p["status"]          = pr.status if pr else "not_started"
                    p["rating"]          = (pr.rating if pr and pr.rating else 0)
                    p["difficulty_felt"] = (pr.difficulty_felt if pr and pr.difficulty_felt else "")
                    p["comment"]         = (pr.comment if pr and pr.comment else "")

                built.append({
                    "id":            c.id,
                    "genre":         c.genre,
                    "time_to_read":  c.time_to_read,
                    "difficulty":    c.difficulty,
                    "overall_arc":   c.overall_arc,
                    "created_at":    c.created_at.strftime("%b %d, %Y"),
                    "picks":         picks,
                    "summary":       summary,
                })

        self.dashboard_curricula          = built
        self.dashboard_total_finished     = total_finished
        self.dashboard_total_picks        = total_picks
        self.dashboard_total_reading      = total_reading
        self.dashboard_finished_this_week = finished_this_week


def _attach_progress(result, user_id: str) -> list[dict]:
    """Build the list[dict] State.picks expects, merging in the Progress row
    for each pick (status, rating, difficulty_felt, comment).

    Returns picks with sensible defaults if no Progress row exists (e.g. CLI
    runs without a user_id, or in tests)."""
    picks = [p.model_dump() for p in result.picks]

    if not (result.db_id and user_id):
        for p in picks:
            p.update(status="not_started", rating=0, difficulty_felt="", comment="")
        return picks

    # Materialize all needed attributes inside the session so the dicts
    # we use afterward don't trip DetachedInstanceError.
    with rx.session() as session:
        rows = session.exec(
            select(Progress).where(Progress.curriculum_id == result.db_id)
        ).all()
        by_book = {
            r.book_id: {
                "status": r.status,
                "rating": r.rating or 0,
                "difficulty_felt": r.difficulty_felt or "",
                "comment": r.comment or "",
            }
            for r in rows
        }

    for p in picks:
        pr = by_book.get(p["book_id"])
        if pr:
            p.update(pr)
        else:
            p.update(status="not_started", rating=0, difficulty_felt="", comment="")
    return picks