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


# Stepped messages shown under the loading spinner. Advances every TICK_SEC
# while the generation task is running — pseudo-progress, not tied to actual
# internal phases of the pipeline (those happen inside a single to_thread
# call we can't easily instrument from the outside).
LOADING_STAGES = [
    "Extracting filters from your survey…",
    "Searching the catalog…",
    "Picking the right five books…",
    "Writing the reasoning…",
]
TICK_SEC = 2.5


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
    # Human-readable elapsed-time label like "Reading for 3 days" or
    # "Finished in 5 days". Empty string when status is not_started.
    days_label: str


class DashboardCurriculum(TypedDict):
    id: int
    genre: str
    time_to_read: str
    difficulty: str
    overall_arc: str
    created_at: str
    picks: list[DashboardPick]
    # Same picks, but the "hero" (earliest reading, else earliest not-started,
    # else lowest week) is moved to index 0. The Dashboard tab's 2D grid
    # renders this list so the hero spans both columns at the top.
    picks_ordered: list[DashboardPick]
    summary: ProgressSummary
    # Soft-delete flag. Archived rows live in the Finished tab.
    is_archived: bool


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
    # PK of the curriculum currently being viewed on the home page after
    # generation. 0 means no curriculum loaded.
    curriculum_id: int = 0

    # Cookie-persisted id of the user's chosen *active* curriculum — the one
    # the /dashboard tab tracks. Stored as a string for cookie compatibility;
    # parsed to int when querying. "0" means no active curriculum yet.
    active_curriculum_id: str = rx.Cookie("0")

    # Loaded view of the active curriculum (0-or-1-item list so rx.foreach
    # works without conditional branches in templates).
    active_curriculum_list: list[DashboardCurriculum] = []

    # Dashboard data: list of past curricula with their progress summaries.
    # Typed so rx.foreach can introspect nested keys like
    # c["summary"]["finished"] in templates.
    dashboard_curricula: list[DashboardCurriculum] = []
    # Same data, split for the /curricula tabs:
    #   active   = at least one pick still not_started / reading / abandoned
    #   finished = every pick has status == "finished"
    dashboard_curricula_active: list[DashboardCurriculum] = []
    dashboard_curricula_finished: list[DashboardCurriculum] = []
    # Header stat counts. All derived from progress rows in one pass.
    dashboard_total_finished: int = 0
    dashboard_total_picks: int = 0
    dashboard_total_reading: int = 0
    dashboard_finished_this_week: int = 0

    # UI status
    is_loading: bool = False
    # Stepped status line shown under the loading spinner — advances through
    # LOADING_STAGES on a timer while the generation task runs in the
    # background. Makes the wait feel like progress, even though we can't
    # report on the real internal phases of generate_for_survey.
    loading_stage: str = ""
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
            self.loading_stage = LOADING_STAGES[0]
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

        # Kick off the real work as a parallel task so we can tick through
        # the LOADING_STAGES messages while it runs. asyncio.shield prevents
        # wait_for(timeout) from cancelling the inner generation.
        work = asyncio.create_task(
            asyncio.to_thread(
                generate_for_survey,
                genre, time_to_read, difficulty,
                already_read_titles,
                user_id,
            )
        )

        try:
            # Pseudo-progress ticker — every TICK_SEC, advance the stage if
            # the work hasn't finished. Bounded by an overall 60s timeout.
            stage_idx = 0
            elapsed = 0.0
            while not work.done():
                if elapsed >= 60.0:
                    work.cancel()
                    raise asyncio.TimeoutError()
                try:
                    await asyncio.wait_for(asyncio.shield(work), timeout=TICK_SEC)
                except asyncio.TimeoutError:
                    elapsed += TICK_SEC
                    if stage_idx + 1 < len(LOADING_STAGES):
                        stage_idx += 1
                        async with self:
                            self.loading_stage = LOADING_STAGES[stage_idx]

            # work is done — .result() raises if generate_for_survey raised.
            result = work.result()

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
        except asyncio.TimeoutError:
            async with self:
                self.error = "Generation took too long. Please try again."
        except Exception as e:
            async with self:
                self.error = f"Unexpected error ({type(e).__name__}): {e}"
        finally:
            async with self:
                self.is_loading = False
                self.loading_stage = ""

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
        self.loading_stage = ""

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
        # Update the human-readable days label inline so the UI reflects
        # the change immediately. Full recompute happens on the next page
        # load via _make_days_label.
        live_label = {
            "reading":   "Reading today",
            "finished":  "Finished today",
            "abandoned": "Abandoned",
        }.get(new_status, "")
        self._propagate_pick_change(
            curriculum_id, book_id,
            status=new_status, days_label=live_label,
        )
        # Refresh the history page so its summary counts re-tally (its
        # picks_ordered also recomputes — fine, that page only shows the
        # collapsed accordion, no hero visible to jump). The active
        # dashboard intentionally does NOT reload here: _propagate_pick_change
        # already updated its picks + summary in place WITHOUT touching
        # picks_ordered, so the hero card stays put while the user finishes
        # entering rating / difficulty / comment.
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
        """Reflect a per-pick change in all three view-bound lists.

        On the active /dashboard view, we update the pick fields IN PLACE
        within picks_ordered (no re-sort). This keeps the hero card from
        jumping out from under the user mid-edit — they can mark a book
        Finished and then enter rating / difficulty / comment without the
        card swapping. The hero re-computes naturally on the next
        /dashboard mount (load_active_curriculum)."""

        # --- State.picks (generation page) ---
        if self.curriculum_id == curriculum_id:
            self.picks = [
                {**p, **fields} if p["book_id"] == book_id else p
                for p in self.picks
            ]

        # --- State.dashboard_curricula (history page) ---
        # The history list shows curricula collapsed; layout swapping there
        # doesn't matter, but we update summary counts on status changes.
        if self.dashboard_curricula:
            self.dashboard_curricula = [
                _patch_curriculum(c, book_id, fields)
                if c["id"] == curriculum_id else c
                for c in self.dashboard_curricula
            ]

        # --- State.active_curriculum_list (Dashboard tab) ---
        if self.active_curriculum_list:
            self.active_curriculum_list = [
                _patch_curriculum(c, book_id, fields, preserve_ordering=True)
                if c["id"] == curriculum_id else c
                for c in self.active_curriculum_list
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
    def delete_curriculum(self, curriculum_id: int):
        """Permanently delete the curriculum + its Progress rows. The row
        just disappears from whichever tab it was on. If it happened to be
        the active curriculum, the cookie clears too."""
        if not curriculum_id or not self.user_id:
            return

        with rx.session() as session:
            for pr in session.exec(
                select(Progress).where(Progress.curriculum_id == curriculum_id)
            ).all():
                session.delete(pr)
            curr = session.exec(
                select(CurriculumRow)
                .where(CurriculumRow.id == curriculum_id)
                .where(CurriculumRow.user_id == self.user_id)
            ).first()
            if curr is not None:
                session.delete(curr)
            session.commit()

        if self.active_curriculum_id == str(curriculum_id):
            self.active_curriculum_id = "0"
            self.active_curriculum_list = []

        self._load_dashboard_data()

    @rx.event
    def accept_curriculum(self, curriculum_id: int = 0):
        """Mark a curriculum as the user's active one and navigate to
        /dashboard. Called without an arg from the post-generation block
        (uses self.curriculum_id) or with an explicit id from the
        /curricula list (any past curriculum can become active)."""
        target = curriculum_id or self.curriculum_id
        if not target:
            return
        self.active_curriculum_id = str(target)
        return rx.redirect("/dashboard")

    @rx.event
    def load_active_curriculum(self):
        """Public event handler — wraps the loader so the per-pick handlers
        can refresh the active curriculum without re-decorating."""
        self._load_active_curriculum_data()

    def _load_active_curriculum_data(self):
        """Populate active_curriculum_list with the single curriculum
        identified by active_curriculum_id (or empty if none set)."""
        if not self.user_id or self.active_curriculum_id in ("", "0"):
            self.active_curriculum_list = []
            return
        try:
            target_id = int(self.active_curriculum_id)
        except ValueError:
            self.active_curriculum_list = []
            return

        with rx.session() as session:
            row = session.exec(
                select(CurriculumRow)
                .where(CurriculumRow.id == target_id)
                .where(CurriculumRow.user_id == self.user_id)
            ).first()
            if row is None:
                self.active_curriculum_list = []
                return

            progress_rows = session.exec(
                select(Progress).where(Progress.curriculum_id == row.id)
            ).all()
            statuses = [pr.status for pr in progress_rows]
            summary = {
                "total":       len(statuses),
                "finished":    statuses.count("finished"),
                "reading":     statuses.count("reading"),
                "abandoned":   statuses.count("abandoned"),
                "not_started": statuses.count("not_started"),
            }

            by_book = {pr.book_id: pr for pr in progress_rows}
            picks = json.loads(row.picks_json)
            for p in picks:
                pr = by_book.get(p["book_id"])
                p["status"]          = pr.status if pr else "not_started"
                p["rating"]          = (pr.rating if pr and pr.rating else 0)
                p["difficulty_felt"] = (pr.difficulty_felt if pr and pr.difficulty_felt else "")
                p["comment"]         = (pr.comment if pr and pr.comment else "")
                p["days_label"]      = _make_days_label(pr)

            built = {
                "id":            row.id,
                "genre":         row.genre,
                "time_to_read":  row.time_to_read,
                "difficulty":    row.difficulty,
                "overall_arc":   row.overall_arc,
                "created_at":    row.created_at.strftime("%b %d, %Y"),
                "picks":         picks,
                "picks_ordered": _hero_ordering(picks),
                "summary":       summary,
                "is_archived":   bool(getattr(row, "is_archived", False)),
            }

        self.active_curriculum_list = [built]

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
                    p["days_label"]      = _make_days_label(pr)

                built.append({
                    "id":            c.id,
                    "genre":         c.genre,
                    "time_to_read":  c.time_to_read,
                    "difficulty":    c.difficulty,
                    "overall_arc":   c.overall_arc,
                    "created_at":    c.created_at.strftime("%b %d, %Y"),
                    "picks":         picks,
                    # Same picks, hero-first — only the Dashboard tab reads
                    # this; the /curricula list ignores it.
                    "picks_ordered": _hero_ordering(picks),
                    "summary":       summary,
                    "is_archived":   bool(getattr(c, "is_archived", False)),
                })

        self.dashboard_curricula          = built
        # Split for /curricula tabs.
        #   Finished = archived (soft-deleted) OR every pick is finished.
        #   In progress = everything else.
        self.dashboard_curricula_finished = [
            c for c in built
            if c["is_archived"]
            or (
                c["summary"]["total"] > 0
                and c["summary"]["finished"] == c["summary"]["total"]
            )
        ]
        finished_ids = {c["id"] for c in self.dashboard_curricula_finished}
        self.dashboard_curricula_active = [
            c for c in built if c["id"] not in finished_ids
        ]
        self.dashboard_total_finished     = total_finished
        self.dashboard_total_picks        = total_picks
        self.dashboard_total_reading      = total_reading
        self.dashboard_finished_this_week = finished_this_week


def _hero_ordering(picks: list[dict]) -> list[dict]:
    """Reorder a list of picks so the 'hero' pick is at index 0.

    Hero priority:
      1. Earliest week (by `week`) where status == 'reading'.
      2. Earliest week where status == 'not_started'.
      3. The earliest pick overall.

    Other picks keep their week order relative to each other after the hero
    is hoisted out — that way the 2x2 grid below the hero still reads
    naturally (skipping the week chosen as hero)."""
    if not picks:
        return picks
    by_week = sorted(picks, key=lambda p: p["week"])
    hero = next((p for p in by_week if p.get("status") == "reading"), None)
    if hero is None:
        hero = next((p for p in by_week if p.get("status") == "not_started"), None)
    if hero is None:
        hero = by_week[0]
    return [hero] + [p for p in by_week if p["book_id"] != hero["book_id"]]


def _bump_summary(summary: dict, old_status: str, new_status: str) -> dict:
    """Return a copy of `summary` with the status counters adjusted to
    reflect one pick transitioning old_status -> new_status."""
    if old_status == new_status:
        return summary
    out = dict(summary)
    if old_status in out:
        out[old_status] = max(0, out[old_status] - 1)
    if new_status in out:
        out[new_status] = out.get(new_status, 0) + 1
    return out


def _patch_curriculum(c: dict, book_id: str, fields: dict,
                     preserve_ordering: bool = False) -> dict:
    """Apply `fields` to the pick matching `book_id` inside both `picks`
    and `picks_ordered` (when present). If `fields` includes `status`,
    also adjust the summary counters so the in-memory progress totals
    stay in sync without re-querying the DB.

    `preserve_ordering` keeps picks_ordered in its existing order — used
    on the Dashboard tab so the hero card doesn't jump mid-edit."""
    is_status_change = "status" in fields
    old_status = next(
        (p["status"] for p in c.get("picks", []) if p["book_id"] == book_id),
        None,
    )

    new_picks = [
        {**p, **fields} if p["book_id"] == book_id else p
        for p in c.get("picks", [])
    ]

    if "picks_ordered" in c:
        if preserve_ordering:
            new_picks_ordered = [
                {**p, **fields} if p["book_id"] == book_id else p
                for p in c["picks_ordered"]
            ]
        else:
            new_picks_ordered = _hero_ordering(new_picks)
    else:
        new_picks_ordered = None

    new_summary = c.get("summary", {})
    if is_status_change and old_status is not None:
        new_summary = _bump_summary(new_summary, old_status, fields["status"])

    out = {**c, "picks": new_picks, "summary": new_summary}
    if new_picks_ordered is not None:
        out["picks_ordered"] = new_picks_ordered
    return out


def _make_days_label(pr) -> str:
    """Human-readable elapsed-time label for a single Progress row, used by
    the Dashboard 'Reading for N days' / 'Finished in N days' sub-line.

    Returns an empty string when there's no meaningful time signal yet
    (e.g. status == 'not_started', or 'reading' with no started_at)."""
    if pr is None:
        return ""
    now = datetime.utcnow()
    if pr.status == "reading" and pr.started_at is not None:
        days = (now - pr.started_at).days
        return "Reading today" if days == 0 else f"Reading for {days} day{'s' if days != 1 else ''}"
    if pr.status == "finished" and pr.started_at is not None and pr.finished_at is not None:
        days = (pr.finished_at - pr.started_at).days
        return "Finished same day" if days <= 0 else f"Finished in {days} day{'s' if days != 1 else ''}"
    if pr.status == "abandoned":
        return "Abandoned"
    return ""


def _attach_progress(result, user_id: str) -> list[dict]:
    """Build the list[dict] State.picks expects, merging in the Progress row
    for each pick (status, rating, difficulty_felt, comment).

    Returns picks with sensible defaults if no Progress row exists (e.g. CLI
    runs without a user_id, or in tests)."""
    picks = [p.model_dump() for p in result.picks]

    if not (result.db_id and user_id):
        for p in picks:
            p.update(status="not_started", rating=0, difficulty_felt="", comment="", days_label="")
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
                "days_label": _make_days_label(r),
            }
            for r in rows
        }

    for p in picks:
        pr = by_book.get(p["book_id"])
        if pr:
            p.update(pr)
        else:
            p.update(status="not_started", rating=0, difficulty_felt="", comment="", days_label="")
    return picks