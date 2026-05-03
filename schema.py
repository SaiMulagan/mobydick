from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class EraRange(BaseModel):
    start: int = Field(ge=1000, le=2100)
    end:   int = Field(ge=1000, le=2100)

    @model_validator(mode="after")
    def _check_order(self):
        if self.start > self.end:
            raise ValueError(f"era.start ({self.start}) > era.end ({self.end})")
        return self


class PageRange(BaseModel):
    min: int = Field(ge=10, le=2000)
    max: int = Field(ge=10, le=2000)

    @model_validator(mode="after")
    def _check_order(self):
        if self.min > self.max:
            raise ValueError(f"page_range.min ({self.min}) > page_range.max ({self.max})")
        return self


class SurveyFilters(BaseModel):
    is_recognized_topic: bool
    topic_keywords: list[str] = Field(min_length=1, max_length=5)
    era: Optional[EraRange] = None
    page_range: PageRange
    difficulty: Literal["low", "medium", "high"]
    language_codes: list[str] = Field(
        default_factory=lambda: ["eng"], min_length=1, max_length=5
    )


class CurriculumPick(BaseModel):
    book_id: str
    title: str
    author: str
    week: int = Field(ge=1, le=52)
    # Prompt asks for ~1 sentence under 180 chars. Max here is a safety net
    # (Gemini's JSON-mode honors structure but not string-length constraints
    # strictly — give 25% wiggle room so we don't crash when it overshoots).
    reason: str = Field(min_length=20, max_length=300)


class Curriculum(BaseModel):
    picks: list[CurriculumPick] = Field(min_length=5, max_length=5)
    # Prompt asks for 1-2 sentences under 250 chars; max is a safety net.
    overall_arc: str = Field(min_length=30, max_length=400)