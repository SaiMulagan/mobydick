import asyncio
import reflex as rx

from pipeline import generate_for_survey


class State(rx.State):
    # Form inputs
    genre: str = ""
    time_to_read: str = ""
    difficulty: str = ""

    # Result fields (flat — easier for Reflex to serialize than a nested model)
    overall_arc: str = ""
    picks: list[dict] = []   # each item: {"week": int, "title": str, "author": str, "reason": str}

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

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    generate_for_survey, genre, time_to_read, difficulty
                ),
                timeout=60.0,
            )
            async with self:
                self.overall_arc = result.overall_arc
                self.picks = [p.model_dump() for p in result.picks]
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
        self.overall_arc = ""
        self.picks = []
        self.error = ""