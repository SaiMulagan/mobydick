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
            style={"font_style": "italic", "color": WINE_SOFT, "margin_bottom": "8px"},
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

        size="3",
        width="100%",
        style={
            "background_color": CARD_BG,
            "border_left": f"4px solid {WINE}",
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
            placeholder="e.g. 18th century Russian literature",
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
                    "Building your curriculum… this takes 5–15 seconds.",
                    size="2",
                    style={"color": WINE_SOFT, "font_style": "italic"},
                ),
                align="center",
                spacing="2",
                margin_top="4",
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
                rx.button(
                    "Try another",
                    on_click=State.reset_form,
                    variant="outline",
                    size="3",
                    margin_top="2",
                    style={"color": WINE, "border_color": WINE},
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
        link("Generate", "/", "generate"),
        link("Your curricula", "/dashboard", "dashboard"),
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

        # Progress summary row
        rx.hstack(
            progress_pill("FINISHED", c["summary"]["finished"], WINE),
            progress_pill("READING",  c["summary"]["reading"],  WINE_SOFT),
            progress_pill("ABANDONED", c["summary"]["abandoned"], "#a06070"),
            rx.spacer(),
            rx.text(
                c["summary"]["finished"], " / ", c["summary"]["total"], " books",
                size="2",
                style={"color": INK, "font_weight": "600"},
            ),
            spacing="4",
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
            "border_left": f"4px solid {WINE}",
            "border_radius": "6px",
        },
    )


def dashboard() -> rx.Component:
    return rx.box(
        nav_bar(active="dashboard"),
        rx.center(
            rx.vstack(
                rx.heading(
                    "Your curricula",
                    size="8",
                    style={**DISPLAY_STYLE, "font_size": "44px"},
                ),
                rx.cond(
                    State.dashboard_total_picks > 0,
                    rx.text(
                        State.dashboard_total_finished, " of ",
                        State.dashboard_total_picks, " books finished across all curricula.",
                        size="3",
                        style={
                            "font_family": DISPLAY_FONT,
                            "font_style": "italic",
                            "color": WINE_SOFT,
                            "margin_bottom": "16px",
                        },
                    ),
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
                rx.foreach(State.dashboard_curricula, curriculum_summary_card),
                spacing="4",
                width="100%",
                max_width="640px",
                padding="6",
            ),
            min_height="80vh",
            width="100%",
        ),
        on_mount=[State.hydrate_user, State.load_dashboard],
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
app.add_page(dashboard, route="/dashboard", title="Your curricula · Moby Dicks")
