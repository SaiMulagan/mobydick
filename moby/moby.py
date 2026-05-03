import reflex as rx

from .state import State

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


def pick_card(pick) -> rx.Component:
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
                rx.foreach(State.picks, pick_card),
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


def index() -> rx.Component:
    return rx.box(
        rx.center(survey_form(), min_height="100vh", width="100%"),
        style={
            "background_color": CREAM,
            "min_height": "100vh",
            "color": INK,
            "font_family": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
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
