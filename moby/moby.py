import reflex as rx

from .state import State

def pick_card(pick) -> rx.Component:
    return rx.card(
        rx.text(
            "Week ", pick["week"],
            size="2", weight="bold", color_scheme="blue",
        ),
        rx.heading(pick["title"], size="4", margin_top="2"),
        rx.text(pick["author"], color_scheme="gray", size="3"),
        rx.text(pick["reason"], size="3", margin_top="2"),
        size="3",
        width="100%",
    )

def survey_form() -> rx.Component:
    return rx.vstack(
        rx.heading("Moby Dicks", size="8"),
        rx.text(
            "Tell us what to read. We'll build a five-book curriculum.",
            color_scheme="gray",
        ),

        rx.text("Genre / topic", weight="bold"),
        rx.input(
            value=State.genre,
            on_change=State.set_genre,
            placeholder="e.g. 18th century Russian literature",
            size="3",
            width="100%",
        ),

        rx.text("How much time?", weight="bold"),
        rx.input(
            value=State.time_to_read,
            on_change=State.set_time_to_read,
            placeholder="e.g. commute, evening, weekend, long project",
            size="3",
            width="100%",
        ),

        rx.text("Difficulty", weight="bold"),
        rx.input(
            value=State.difficulty,
            on_change=State.set_difficulty,
            placeholder="e.g. easy, moderate, challenging",
            size="3",
            width="100%",
        ),

        rx.button(
            "Generate curriculum",
            on_click=State.submit,
            size="3",
            width="100%",
            loading=State.is_loading,
            disabled=State.is_loading,
        ),

        rx.cond(
            State.is_loading,
            rx.vstack(
                rx.spinner(size="3"),
                rx.text(
                    "Building your curriculum… this takes 5–15 seconds.",
                    size="2",
                    color_scheme="gray",
                ),
                align="center",
                spacing="2",
                margin_top="4",
            ),
        ),

        rx.cond(
            State.error != "",
            rx.callout(State.error, icon="triangle_alert", color_scheme="red"),
        ),

        rx.cond(
            State.overall_arc != "",
            rx.vstack(
                rx.divider(margin_y="4"),
                rx.heading("Your curriculum", size="6"),
                rx.text(State.overall_arc, color_scheme="gray", size="3"),
                rx.foreach(State.picks, pick_card),
                rx.button(
                    "Try another",
                    on_click=State.reset_form,
                    variant="outline",
                    size="3",
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


def index() -> rx.Component:
    return rx.center(survey_form(), min_height="100vh")


app = rx.App()
app.add_page(index, title="Moby Dicks")