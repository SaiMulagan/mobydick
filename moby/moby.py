import reflex as rx

from .state import State
import db  # noqa: F401  -- registers SQLModel tables with Alembic metadata

# ---------------------------------------------------------------------------
# Theme constants — pulled from the Milestone 5 deck.
# ---------------------------------------------------------------------------
WINE       = "#6B2A3E"   # primary burgundy from deck title slide / accents
WINE_SOFT  = "#8A4856"   # secondary wine for subtitles
WINE_DARK  = "#3a1f24"   # dark wine for body-on-cream titles
CREAM      = "#EDE3D2"   # parchment page background
CARD_BG    = "#FBF8F2"   # off-white card surface
INK        = "#2c1d22"   # body text on cream

DISPLAY_FONT = "'Playfair Display', Georgia, serif"

LABEL_STYLE = {
    "letter_spacing": "0.18em",
    "text_transform": "uppercase",
    "color": WINE,
    "font_size": "11px",
    "font_weight": "700",
}

DISPLAY_STYLE = {
    "font_family": DISPLAY_FONT,
    "font_style": "italic",
    "font_weight": "700",
    "color": WINE,
    "line_height": "1.05",
    "letter_spacing": "-0.01em",
}


def pick_card(pick, curriculum_id) -> rx.Component:
    """Editable pick card. `curriculum_id` is required so handlers know
    which Progress row to mutate — pass State.curriculum_id on the
    generation page; pass each curriculum's id on the dashboard."""
    return rx.card(
        rx.text("Week ", pick["week"], style=LABEL_STYLE),
        rx.heading(
            pick["title"],
            size="5",
            margin_top="1",
            style={
                "font_family": DISPLAY_FONT,
                "font_style": "italic",
                "font_weight": "700",
                "color": WINE_DARK,
                "line_height": "1.15",
            },
        ),
        rx.text(
            pick["author"],
            size="3",
            style={"font_style": "italic", "color": WINE_SOFT},
        ),
        # "Reading for N days" / "Finished in N days" — visible only after
        # the user has started or completed the book.
        rx.cond(
            pick["days_label"] != "",
            rx.text(
                pick["days_label"],
                size="1",
                style={
                    "color": WINE,
                    "font_weight": "700",
                    "letter_spacing": "0.06em",
                    "text_transform": "uppercase",
                    "margin_top": "2px",
                    "margin_bottom": "8px",
                },
            ),
            rx.box(style={"margin_bottom": "8px"}),  # spacer when no label
        ),
        rx.text(pick["reason"], size="3", style={"color": INK, "line_height": "1.55"}),

        # ---- Status select ----------------------------------------------
        rx.hstack(
            rx.text("STATUS", style={**LABEL_STYLE, "font_size": "10px"}),
            rx.select.root(
                rx.select.trigger(variant="surface", radius="medium"),
                rx.select.content(
                    rx.select.item("Not started", value="not_started"),
                    rx.select.item("Reading",     value="reading"),
                    rx.select.item("Finished",    value="finished"),
                    rx.select.item("Abandoned",   value="abandoned"),
                ),
                value=pick["status"],
                on_change=lambda v: State.set_pick_status(curriculum_id, pick["book_id"], v),
                size="1",
            ),
            spacing="2",
            align="center",
            margin_top="3",
        ),

        # ---- Check-in controls (only after a status is picked) ----------
        rx.cond(
            pick["status"] != "not_started",
            rx.vstack(
                rx.hstack(
                    rx.text("RATING", style={**LABEL_STYLE, "font_size": "10px"}),
                    rx.select.root(
                        rx.select.trigger(variant="surface", radius="medium"),
                        rx.select.content(
                            rx.select.item("—",     value="0"),
                            rx.select.item("★",     value="1"),
                            rx.select.item("★★",    value="2"),
                            rx.select.item("★★★",   value="3"),
                            rx.select.item("★★★★",  value="4"),
                            rx.select.item("★★★★★", value="5"),
                        ),
                        value=pick["rating"].to_string(),
                        on_change=lambda v: State.set_pick_rating(curriculum_id, pick["book_id"], v),
                        size="1",
                    ),
                    rx.text("DIFFICULTY", style={**LABEL_STYLE, "font_size": "10px", "margin_left": "12px"}),
                    rx.select.root(
                        rx.select.trigger(variant="surface", radius="medium", placeholder="—"),
                        rx.select.content(
                            rx.select.item("Too easy",   value="too_easy"),
                            rx.select.item("Just right", value="just_right"),
                            rx.select.item("Too dense",  value="too_dense"),
                            rx.select.item("Abandoned",  value="abandoned"),
                        ),
                        value=pick["difficulty_felt"],
                        on_change=lambda v: State.set_pick_difficulty_felt(curriculum_id, pick["book_id"], v),
                        size="1",
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text_area(
                    value=pick["comment"],
                    # on_change keeps the textarea responsive (in-memory only);
                    # on_blur is what actually writes to the DB.
                    on_change=lambda v: State.update_pick_comment_draft(curriculum_id, pick["book_id"], v),
                    on_blur=lambda v: State.commit_pick_comment(curriculum_id, pick["book_id"], v),
                    placeholder="Notes — what worked, what didn't (saved when you click away)",
                    size="2",
                    rows="2",
                    width="100%",
                    style={"margin_top": "8px"},
                ),
                spacing="2",
                align="start",
                width="100%",
                margin_top="2",
            ),
        ),

        # ---- "More like this" — appears only on finished picks ----------
        rx.cond(
            pick["status"] == "finished",
            rx.button(
                "More like this →",
                on_click=lambda: State.more_like_this(curriculum_id, pick["book_id"]),
                variant="outline",
                size="2",
                style={
                    "color": WINE,
                    "border_color": WINE,
                    "margin_top": "10px",
                    "letter_spacing": "0.04em",
                },
            ),
        ),

        size="3",
        width="100%",
        style={
            "background_color": CARD_BG,
            # inset shadow instead of border-left so the wine bar respects
            # the card's rounded corners (border-left would extend past the
            # radius and overhang at the top/bottom).
            "box_shadow": f"inset 4px 0 0 {WINE}",
            "border_radius": "6px",
        },
    )


def field_label(text: str) -> rx.Component:
    return rx.text(text, style=LABEL_STYLE)


def survey_form() -> rx.Component:
    return rx.vstack(
        # ---- Hero --------------------------------------------------------
        rx.heading(
            "Moby Dicks",
            size="9",
            style={**DISPLAY_STYLE, "font_size": "64px"},
        ),
        rx.text(
            "We don't just recommend books you'll like. "
            "We recommend books you'll actually finish.",
            size="4",
            style={
                "font_family": DISPLAY_FONT,
                "font_style": "italic",
                "color": WINE_SOFT,
                "line_height": "1.4",
                "margin_bottom": "16px",
            },
        ),

        # ---- Form fields -------------------------------------------------
        field_label("Genre / topic"),
        rx.input(
            value=State.genre,
            on_change=State.set_genre,
            placeholder="e.g. Japanese magical realism",
            size="3",
            width="100%",
        ),

        field_label("How much time?"),
        rx.input(
            value=State.time_to_read,
            on_change=State.set_time_to_read,
            placeholder="e.g. commute, evening, weekend, long project",
            size="3",
            width="100%",
        ),

        field_label("Difficulty"),
        rx.input(
            value=State.difficulty,
            on_change=State.set_difficulty,
            placeholder="e.g. easy, moderate, challenging",
            size="3",
            width="100%",
        ),

        field_label("Books you've already read (optional)"),
        rx.text_area(
            value=State.already_read,
            on_change=State.set_already_read,
            placeholder="One title per line, e.g.:\nCrime and Punishment\nThe Brothers Karamazov",
            size="3",
            width="100%",
            rows="3",
        ),

        # ---- Submit ------------------------------------------------------
        rx.button(
            "Generate curriculum",
            on_click=State.submit,
            size="3",
            width="100%",
            loading=State.is_loading,
            disabled=State.is_loading,
            style={
                "background_color": WINE,
                "color": CREAM,
                "font_weight": "600",
                "letter_spacing": "0.04em",
                "margin_top": "8px",
            },
        ),

        # ---- Loading -----------------------------------------------------
        rx.cond(
            State.is_loading,
            rx.vstack(
                rx.spinner(size="3", style={"color": WINE}),
                rx.text(
                    State.loading_stage,
                    size="2",
                    style={
                        "color": WINE_SOFT,
                        "font_style": "italic",
                        "text_align": "center",
                    },
                ),
                align="center",
                spacing="2",
                margin_top="4",
                # span the full parent width so align="center" actually
                # centers within the form column (otherwise the vstack
                # hugs its content and sits left-aligned).
                width="100%",
            ),
        ),

        # ---- Error -------------------------------------------------------
        rx.cond(
            State.error != "",
            rx.callout(
                State.error,
                icon="triangle_alert",
                color_scheme="ruby",
                style={"margin_top": "8px"},
            ),
        ),

        # ---- Result ------------------------------------------------------
        rx.cond(
            State.overall_arc != "",
            rx.vstack(
                rx.divider(
                    margin_y="6",
                    style={"background_color": WINE, "height": "1px", "opacity": "0.3"},
                ),
                rx.text("Your curriculum", style=LABEL_STYLE),
                rx.heading(
                    "A reading order built around what you'll finish.",
                    size="6",
                    style={**DISPLAY_STYLE, "color": WINE},
                ),
                rx.text(
                    State.overall_arc,
                    size="3",
                    style={
                        "color": INK,
                        "font_style": "italic",
                        "line_height": "1.6",
                        "margin_bottom": "8px",
                    },
                ),
                rx.foreach(State.picks, lambda p: pick_card(p, State.curriculum_id)),
                rx.hstack(
                    rx.button(
                        "Accept this curriculum →",
                        # Lambda wrapper so Reflex doesn't try to pass the
                        # PointerEventInfo into accept_curriculum's optional
                        # curriculum_id parameter (which it expects to be int).
                        on_click=lambda: State.accept_curriculum(),
                        size="3",
                        style={
                            "background_color": WINE,
                            "color": CREAM,
                            "font_weight": "600",
                            "letter_spacing": "0.04em",
                        },
                    ),
                    rx.button(
                        "Try another",
                        on_click=State.reset_form,
                        variant="outline",
                        size="3",
                        style={"color": WINE, "border_color": WINE},
                    ),
                    spacing="3",
                    margin_top="2",
                ),
                spacing="4",
                width="100%",
            ),
        ),

        spacing="3",
        width="100%",
        max_width="640px",
        padding="6",
    )


PAGE_STYLE = {
    "background_color": CREAM,
    "min_height": "100vh",
    "color": INK,
    "font_family": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
}


def nav_bar(active: str) -> rx.Component:
    """Tiny top nav with two links. `active` is the current route key."""
    def link(label: str, route: str, key: str) -> rx.Component:
        is_active = key == active
        return rx.link(
            label,
            href=route,
            style={
                "color": WINE if is_active else WINE_SOFT,
                "text_decoration": "none",
                "font_size": "11px",
                "font_weight": "700",
                "letter_spacing": "0.18em",
                "text_transform": "uppercase",
                "border_bottom": f"2px solid {WINE}" if is_active else "none",
                "padding_bottom": "2px",
            },
        )

    return rx.hstack(
        link("Generate",       "/",           "generate"),
        link("Dashboard",      "/dashboard",  "dashboard"),
        link("Your curricula", "/curricula",  "curricula"),
        spacing="6",
        padding="4",
        width="100%",
        max_width="640px",
        style={"margin": "0 auto"},
    )


def index() -> rx.Component:
    return rx.box(
        nav_bar(active="generate"),
        rx.center(survey_form(), min_height="80vh", width="100%"),
        on_mount=State.hydrate_user,
        style=PAGE_STYLE,
    )


def progress_pill(label: str, count, color: str) -> rx.Component:
    return rx.hstack(
        rx.text(count, weight="bold", style={"color": color}),
        rx.text(label, size="1", style={"color": WINE_SOFT, "letter_spacing": "0.05em"}),
        spacing="1",
        align="baseline",
    )


def _progress_segment(pick) -> rx.Component:
    """One segment of the curriculum progress bar — one per pick.
    Solid wine = finished, diagonal wine stripes over cream = in progress,
    dusty rose = abandoned, muted cream = not started."""
    # "Reading" pattern: 45° wine diagonal stripes layered over the same
    # muted-cream base used for not_started, so the tan shows through the
    # gaps. The two backgrounds are stacked via the shorthand: the gradient
    # paints on top, the cream is the fallback fill.
    reading_stripes = (
        f"repeating-linear-gradient(-45deg, "
        f"{WINE} 0 3px, transparent 3px 8px), "
        f"#E8DDC8"
    )
    return rx.box(
        style={
            "flex": "1",
            "height": "10px",
            "border_radius": "3px",
            "background": rx.match(
                pick["status"],
                ("finished",  WINE),
                ("reading",   reading_stripes),
                ("abandoned", "#a06070"),
                "#E8DDC8",  # not_started — muted cream
            ),
        },
    )


def _momentum_stat(value, label: str, value_color: str = None) -> rx.Component:
    """One large stat tile for the dashboard hero — big serif number on top,
    small tracked-out label below. Matches the deck's slide-4 stat callouts."""
    return rx.vstack(
        rx.text(
            value,
            style={
                "font_family": DISPLAY_FONT,
                "font_style": "italic",
                "font_weight": "700",
                "font_size": "44px",
                "color": value_color or WINE,
                "line_height": "1",
            },
        ),
        rx.text(
            label,
            style={
                **LABEL_STYLE,
                "font_size": "9px",
                "color": WINE_SOFT,
            },
        ),
        spacing="2",
        align="center",
    )


def momentum_widget() -> rx.Component:
    """Dashboard hero row: three side-by-side stats summarizing the user's
    reading activity. Pure aggregates over progress rows already loaded
    in _load_dashboard_data — no extra DB round-trips, no perf cost."""
    return rx.hstack(
        _momentum_stat(State.dashboard_total_finished, "Books finished"),
        _momentum_stat(State.dashboard_total_reading, "In progress", WINE_SOFT),
        _momentum_stat(State.dashboard_finished_this_week, "This week"),
        spacing="6",
        justify="center",
        width="100%",
        style={"margin_bottom": "24px"},
    )


def curriculum_summary_card(c) -> rx.Component:
    return rx.card(
        rx.hstack(
            rx.text(c["genre"], style={**LABEL_STYLE, "letter_spacing": "0.12em"}),
            rx.spacer(),
            rx.text(c["created_at"], size="1", style={"color": WINE_SOFT}),
            width="100%",
        ),
        rx.heading(
            c["overall_arc"],
            size="4",
            style={
                "font_family": DISPLAY_FONT,
                "font_style": "italic",
                "color": WINE_DARK,
                "line_height": "1.25",
                "margin_top": "4px",
            },
        ),

        # ---- Segmented progress bar: one segment per pick, coloured by status
        rx.vstack(
            rx.hstack(
                rx.foreach(c["picks"], _progress_segment),
                spacing="2",
                width="100%",
            ),
            rx.hstack(
                rx.text(
                    c["summary"]["finished"], " of ", c["summary"]["total"], " finished",
                    size="2",
                    style={"color": INK, "font_weight": "600"},
                ),
                rx.spacer(),
                rx.cond(
                    c["summary"]["reading"] > 0,
                    rx.text(
                        c["summary"]["reading"], " in progress",
                        size="2",
                        style={"color": WINE_SOFT, "font_style": "italic"},
                    ),
                ),
                width="100%",
            ),
            spacing="2",
            width="100%",
            margin_top="3",
        ),

        # Editable picks — same component as the generation page so users
        # can mark books finished / rate them / add comments at any time.
        rx.vstack(
            rx.foreach(c["picks"], lambda p: pick_card(p, c["id"])),
            spacing="3",
            width="100%",
            margin_top="3",
        ),

        size="3",
        width="100%",
        style={
            "background_color": CARD_BG,
            # inset shadow instead of border-left so the wine bar respects
            # the card's rounded corners (border-left would extend past the
            # radius and overhang at the top/bottom).
            "box_shadow": f"inset 4px 0 0 {WINE}",
            "border_radius": "6px",
        },
    )


def _curricula_row(c) -> rx.Component:
    """One collapsed-by-default accordion row for the /curricula list.

    Trigger row: genre + (optional) ACTIVE badge + delete icon + date.
    Same layout for both tabs so switching In progress ↔ Finished never
    shifts columns.

    Expanding shows the full curriculum_summary_card plus a 'Make this
    active →' button when the row isn't already active. Delete lives in
    the trigger's trash icon (not in the expanded content) and stops
    propagation so it doesn't toggle the accordion."""
    is_active = c["id"].to_string() == State.active_curriculum_id

    return rx.accordion.item(
        rx.accordion.header(
            rx.accordion.trigger(
                rx.hstack(
                    rx.text(c["genre"], style={**LABEL_STYLE, "letter_spacing": "0.12em"}),
                    rx.cond(
                        is_active,
                        rx.text(
                            "✓ ACTIVE",
                            style={
                                **LABEL_STYLE,
                                "font_size": "9px",
                                "color": WINE,
                                "margin_left": "8px",
                            },
                        ),
                    ),
                    rx.spacer(),
                    # Delete: small trash icon. stop_propagation keeps the
                    # click from also toggling the accordion. Shown on every
                    # row (both tabs) so the layout doesn't shift.
                    rx.button(
                        rx.icon("trash-2", size=14),
                        on_click=State.delete_curriculum(c["id"]).stop_propagation,
                        variant="ghost",
                        size="1",
                        color_scheme="ruby",
                        style={"padding": "4px", "min_width": "auto"},
                        aria_label="Delete curriculum",
                    ),
                    rx.text(
                        c["created_at"],
                        size="2",
                        style={"color": WINE_SOFT, "font_style": "italic"},
                    ),
                    rx.accordion.icon(),
                    spacing="3",
                    width="100%",
                    align="center",
                ),
                # Kill the default hover background — the trash icon is now
                # the affordance for any row-level action.
                style={
                    "_hover": {"background_color": "transparent"},
                    "cursor": "pointer",
                },
            ),
        ),
        rx.accordion.content(
            rx.vstack(
                curriculum_summary_card(c),
                rx.cond(
                    ~is_active,
                    rx.button(
                        "Make this active →",
                        on_click=lambda: State.accept_curriculum(c["id"]),
                        size="3",
                        style={
                            "background_color": WINE,
                            "color": CREAM,
                            "font_weight": "600",
                            "letter_spacing": "0.04em",
                            "margin_top": "8px",
                            "align_self": "flex-start",
                        },
                    ),
                ),
                spacing="3",
                width="100%",
            ),
        ),
        value=c["id"].to_string(),
    )


def _curricula_accordion(curricula_var, empty_msg: str) -> rx.Component:
    """Helper: wrap a list of curricula in an accordion, or show the
    given empty-state text if the list is empty."""
    return rx.cond(
        curricula_var.length() > 0,
        rx.accordion.root(
            rx.foreach(curricula_var, _curricula_row),
            type="single",
            collapsible=True,
            width="100%",
            variant="ghost",
        ),
        rx.text(
            empty_msg,
            size="3",
            style={
                "font_family": DISPLAY_FONT,
                "font_style": "italic",
                "color": WINE_SOFT,
                "margin_top": "12px",
            },
        ),
    )


def curricula_history() -> rx.Component:
    """The 'Your curricula' page — collapsed list of every curriculum the
    user has generated. Click a row to expand the full detail. Each can be
    promoted to the active /dashboard curriculum."""
    return rx.box(
        nav_bar(active="curricula"),
        # rx.flex with align="start" anchors content to the top so switching
        # tabs (which have different total heights) never re-centers the
        # header/momentum widget vertically. min_height keeps the cream
        # background filling the viewport.
        rx.flex(
            rx.vstack(
                rx.heading(
                    "Your curricula",
                    size="8",
                    style={**DISPLAY_STYLE, "font_size": "44px"},
                ),
                rx.cond(
                    State.dashboard_total_picks > 0,
                    momentum_widget(),
                    rx.text(
                        "No curricula yet. Generate one on the home page to get started.",
                        size="3",
                        style={
                            "font_family": DISPLAY_FONT,
                            "font_style": "italic",
                            "color": WINE_SOFT,
                        },
                    ),
                ),
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger(
                            "In progress",
                            value="active",
                            style={
                                "color": WINE,
                                "font_weight": "600",
                                "letter_spacing": "0.04em",
                            },
                        ),
                        rx.tabs.trigger(
                            "Finished",
                            value="finished",
                            style={
                                "color": WINE,
                                "font_weight": "600",
                                "letter_spacing": "0.04em",
                            },
                        ),
                    ),
                    rx.tabs.content(
                        _curricula_accordion(
                            State.dashboard_curricula_active,
                            empty_msg="No curricula in progress.",
                        ),
                        value="active",
                    ),
                    rx.tabs.content(
                        _curricula_accordion(
                            State.dashboard_curricula_finished,
                            empty_msg="No finished curricula yet.",
                        ),
                        value="finished",
                    ),
                    default_value="active",
                    width="100%",
                ),
                spacing="4",
                width="100%",
                max_width="640px",
                padding="6",
            ),
            align="start",      # anchor to top — no vertical re-centering
            justify="center",   # still horizontally centered
            min_height="80vh",
            width="100%",
        ),
        on_mount=[State.hydrate_user, State.load_dashboard],
        style=PAGE_STYLE,
    )


def active_curriculum_view(c) -> rx.Component:
    """Two-dimensional 'library-shelf' layout for the active curriculum,
    used only on the Dashboard tab. The first pick spans the full width as
    a featured card; the remaining four fill a 2×2 grid below. All five
    picks render with the same `pick_card`, so every check-in control is
    available in both the hero and the grid cells — only the spacing
    changes via CSS grid-column."""
    return rx.vstack(
        # ---- Curriculum context — genre / arc / progress bar ------------
        rx.hstack(
            rx.text(c["genre"], style={**LABEL_STYLE, "letter_spacing": "0.12em"}),
            rx.spacer(),
            rx.text(c["created_at"], size="1", style={"color": WINE_SOFT}),
            width="100%",
        ),
        rx.heading(
            c["overall_arc"],
            size="4",
            style={
                "font_family": DISPLAY_FONT,
                "font_style": "italic",
                "color": WINE_DARK,
                "line_height": "1.25",
                "margin_top": "4px",
            },
        ),
        rx.vstack(
            rx.hstack(
                rx.foreach(c["picks"], _progress_segment),
                spacing="2",
                width="100%",
            ),
            rx.hstack(
                rx.text(
                    c["summary"]["finished"], " of ", c["summary"]["total"], " finished",
                    size="2",
                    style={"color": INK, "font_weight": "600"},
                ),
                rx.spacer(),
                rx.cond(
                    c["summary"]["reading"] > 0,
                    rx.text(
                        c["summary"]["reading"], " in progress",
                        size="2",
                        style={"color": WINE_SOFT, "font_style": "italic"},
                    ),
                ),
                width="100%",
            ),
            spacing="2",
            width="100%",
            margin_top="3",
        ),

        # ---- Section divider + reading-list label -----------------------
        rx.divider(
            margin_y="4",
            style={"background_color": WINE, "height": "1px", "opacity": "0.2"},
        ),
        rx.text("READING LIST", style={**LABEL_STYLE, "font_size": "10px"}),

        # ---- 2D grid driven by picks_ordered: the hero (earliest "reading"
        # else earliest "not_started" else lowest week) is at index 0 and
        # spans both columns. The remaining picks fill the 2x2 below in
        # their original week order. The progress bar above still uses
        # the week-ordered `picks` so segments read left-to-right by week.
        rx.grid(
            rx.foreach(
                c["picks_ordered"],
                lambda p, idx: rx.box(
                    pick_card(p, c["id"]),
                    style={"grid_column": rx.cond(idx == 0, "1 / -1", "auto")},
                ),
            ),
            columns="2",
            spacing="3",
            width="100%",
            margin_top="2",
        ),

        spacing="3",
        width="100%",
    )


def active_dashboard() -> rx.Component:
    """The new 'Dashboard' tab — shows only the accepted active curriculum
    with full check-in controls. Empty state nudges the user back to the
    generate page if they haven't accepted anything yet."""
    return rx.box(
        nav_bar(active="dashboard"),
        rx.center(
            rx.vstack(
                rx.heading(
                    "Now reading",
                    size="8",
                    style={**DISPLAY_STYLE, "font_size": "44px", "margin_bottom": "16px"},
                ),
                rx.cond(
                    State.active_curriculum_list.length() > 0,
                    rx.foreach(State.active_curriculum_list, active_curriculum_view),
                    rx.vstack(
                        rx.text(
                            "No active curriculum yet.",
                            style={
                                "font_family": DISPLAY_FONT,
                                "font_style": "italic",
                                "font_size": "20px",
                                "color": WINE,
                            },
                        ),
                        rx.text(
                            "Generate one on the Generate tab and click "
                            "“Accept this curriculum” to start tracking it here.",
                            size="3",
                            style={"color": INK},
                        ),
                        rx.link(
                            "Go to Generate →",
                            href="/",
                            style={
                                "color": WINE,
                                "font_weight": "700",
                                "letter_spacing": "0.04em",
                                "margin_top": "8px",
                                "text_decoration": "none",
                            },
                        ),
                        spacing="2",
                        align="center",
                        style={"margin_top": "32px"},
                    ),
                ),
                spacing="4",
                width="100%",
                # Wider than the other pages so the 2-column grid has room
                # to breathe — picks render at ~420px each on desktop.
                max_width="900px",
                padding="6",
            ),
            min_height="80vh",
            width="100%",
        ),
        on_mount=[State.hydrate_user, State.load_active_curriculum],
        style=PAGE_STYLE,
    )


app = rx.App(
    theme=rx.theme(
        accent_color="ruby",
        gray_color="sand",
        radius="medium",
        appearance="light",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400;1,700&display=swap",
    ],
)
app.add_page(index, title="Moby Dicks")
app.add_page(active_dashboard, route="/dashboard", title="Dashboard · Moby Dicks")
app.add_page(curricula_history, route="/curricula", title="Your curricula · Moby Dicks")
