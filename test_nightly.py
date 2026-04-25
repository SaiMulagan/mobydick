"""
test_nightly.py — Moby Dicks nightly test suite
Run with:  pytest test_nightly.py -v
Designed to run safely against real infrastructure (read-only) or
fully offline via mocks when GCP credentials are unavailable.
"""

import sys
import types
import json
import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Stub out GCP / MLflow packages that are not installed in CI / nightly env
# ---------------------------------------------------------------------------
def _stub_module(name: str) -> types.ModuleType:
    """Return an existing module or create a new MagicMock stub for it."""
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# google.cloud.bigquery
_google = _stub_module("google")
_google_cloud = _stub_module("google.cloud")
_bq_mod = _stub_module("google.cloud.bigquery")
_bq_mod.Client = MagicMock
_bq_mod.QueryJobConfig = MagicMock
_bq_mod.ScalarQueryParameter = MagicMock
_bq_mod.ArrayQueryParameter = MagicMock
_bq_mod.Row = MagicMock
_google_cloud.bigquery = _bq_mod

# google.genai
_genai_mod = _stub_module("google.genai")
_genai_mod.Client = MagicMock
_genai_types = _stub_module("google.genai.types")
_genai_types.GenerateContentConfig = MagicMock
_genai_mod.types = _genai_types
_google.genai = _genai_mod

# mlflow
_mlflow_mod = _stub_module("mlflow")
_mlflow_pyfunc = _stub_module("mlflow.pyfunc")
_mlflow_pyfunc.load_model = MagicMock()
_mlflow_mod.pyfunc = _mlflow_pyfunc
_mlflow_mod.set_tracking_uri = MagicMock()

# ---------------------------------------------------------------------------
# Test 1 — Schema: EraRange rejects inverted start/end
# ---------------------------------------------------------------------------
class TestEraRangeValidation:
    """EraRange must enforce start <= end."""

    def test_valid_era_accepted(self):
        from schema import EraRange
        era = EraRange(start=1800, end=1899)
        assert era.start == 1800
        assert era.end == 1899

    def test_inverted_era_rejected(self):
        from schema import EraRange
        with pytest.raises((ValidationError, ValueError)):
            EraRange(start=1900, end=1800)

    def test_same_start_end_accepted(self):
        from schema import EraRange
        era = EraRange(start=1850, end=1850)
        assert era.start == era.end


# ---------------------------------------------------------------------------
# Test 2 — Schema: PageRange rejects inverted min/max
# ---------------------------------------------------------------------------
class TestPageRangeValidation:
    """PageRange must enforce min <= max and boundary values."""

    def test_valid_range_accepted(self):
        from schema import PageRange
        pr = PageRange(min=150, max=400)
        assert pr.min < pr.max

    def test_inverted_range_rejected(self):
        from schema import PageRange
        with pytest.raises((ValidationError, ValueError)):
            PageRange(min=500, max=100)

    def test_boundary_values_accepted(self):
        from schema import PageRange
        pr = PageRange(min=10, max=2000)
        assert pr.min == 10
        assert pr.max == 2000

    def test_below_minimum_rejected(self):
        from schema import PageRange
        with pytest.raises((ValidationError, ValueError)):
            PageRange(min=0, max=300)


# ---------------------------------------------------------------------------
# Test 3 — Schema: SurveyFilters requires 1–5 keywords
# ---------------------------------------------------------------------------
class TestSurveyFiltersKeywords:
    """topic_keywords must contain between 1 and 5 items."""

    def _base(self):
        return {
            "is_recognized_topic": True,
            "page_range": {"min": 150, "max": 400},
            "difficulty": "medium",
            "language_codes": ["eng"],
        }

    def test_valid_keywords_accepted(self):
        from schema import SurveyFilters
        data = {**self._base(), "topic_keywords": ["russian", "classic"]}
        sf = SurveyFilters.model_validate(data)
        assert len(sf.topic_keywords) == 2

    def test_empty_keywords_rejected(self):
        from schema import SurveyFilters
        data = {**self._base(), "topic_keywords": []}
        with pytest.raises((ValidationError, ValueError)):
            SurveyFilters.model_validate(data)

    def test_six_keywords_rejected(self):
        from schema import SurveyFilters
        data = {**self._base(), "topic_keywords": ["a", "b", "c", "d", "e", "f"]}
        with pytest.raises((ValidationError, ValueError)):
            SurveyFilters.model_validate(data)

    def test_five_keywords_accepted(self):
        from schema import SurveyFilters
        data = {**self._base(), "topic_keywords": ["a", "b", "c", "d", "e"]}
        sf = SurveyFilters.model_validate(data)
        assert len(sf.topic_keywords) == 5


# ---------------------------------------------------------------------------
# Test 4 — Schema: Curriculum enforces exactly 5 picks
# ---------------------------------------------------------------------------
class TestCurriculumStructure:
    """Curriculum must have exactly 5 picks and a meaningful overall_arc."""

    def _make_pick(self, week: int) -> dict:
        return {
            "book_id": f"book_{week}",
            "title": f"Book {week}",
            "author": "Author Name",
            "week": week,
            "reason": "This book is chosen because it fits the curriculum arc perfectly.",
        }

    def test_exactly_five_picks_accepted(self):
        from schema import Curriculum
        data = {
            "picks": [self._make_pick(i) for i in range(1, 6)],
            "overall_arc": "A well-structured curriculum that builds from accessible entry points to challenging masterworks.",
        }
        c = Curriculum.model_validate(data)
        assert len(c.picks) == 5

    def test_four_picks_rejected(self):
        from schema import Curriculum
        data = {
            "picks": [self._make_pick(i) for i in range(1, 5)],
            "overall_arc": "A well-structured curriculum that builds from accessible entry points to challenging masterworks.",
        }
        with pytest.raises((ValidationError, ValueError)):
            Curriculum.model_validate(data)

    def test_six_picks_rejected(self):
        from schema import Curriculum
        data = {
            "picks": [self._make_pick(i) for i in range(1, 7)],
            "overall_arc": "A well-structured curriculum that builds from accessible entry points to challenging masterworks.",
        }
        with pytest.raises((ValidationError, ValueError)):
            Curriculum.model_validate(data)

    def test_overall_arc_too_short_rejected(self):
        from schema import Curriculum
        data = {
            "picks": [self._make_pick(i) for i in range(1, 6)],
            "overall_arc": "Short.",  # below min_length=30
        }
        with pytest.raises((ValidationError, ValueError)):
            Curriculum.model_validate(data)


# ---------------------------------------------------------------------------
# Test 5 — Schema: CurriculumPick reason length constraints
# ---------------------------------------------------------------------------
class TestCurriculumPickReason:
    """CurriculumPick.reason must be 20–500 characters."""

    def _base_pick(self, reason: str) -> dict:
        return {
            "book_id": "b1",
            "title": "Test Book",
            "author": "Author",
            "week": 1,
            "reason": reason,
        }

    def test_valid_reason_accepted(self):
        from schema import CurriculumPick
        p = CurriculumPick.model_validate(
            self._base_pick("This is a perfectly valid reason for including this book in the list.")
        )
        assert len(p.reason) >= 20

    def test_short_reason_rejected(self):
        from schema import CurriculumPick
        with pytest.raises((ValidationError, ValueError)):
            CurriculumPick.model_validate(self._base_pick("Too short."))

    def test_reason_at_max_length_accepted(self):
        from schema import CurriculumPick
        reason = "x" * 500
        p = CurriculumPick.model_validate(self._base_pick(reason))
        assert len(p.reason) == 500

    def test_reason_exceeds_max_rejected(self):
        from schema import CurriculumPick
        reason = "x" * 501
        with pytest.raises((ValidationError, ValueError)):
            CurriculumPick.model_validate(self._base_pick(reason))


# ---------------------------------------------------------------------------
# Test 6 — Pipeline: generate_for_survey raises on unrecognized topic
# ---------------------------------------------------------------------------
class TestPipelineUnrecognizedTopic:
    """Pipeline must short-circuit and raise ValueError for gibberish input."""

    def test_unrecognized_topic_raises_value_error(self):
        from schema import SurveyFilters, PageRange

        mock_filters = SurveyFilters(
            is_recognized_topic=False,
            topic_keywords=["placeholder"],
            page_range=PageRange(min=150, max=400),
            difficulty="medium",
            language_codes=["eng"],
        )

        with patch("pipeline.extract_filters", return_value=mock_filters):
            from pipeline import generate_for_survey
            with pytest.raises(ValueError, match="couldn't recognize"):
                generate_for_survey("asdfghjkl", "evening", "moderate")

    def test_recognized_topic_does_not_raise_early(self):
        from schema import SurveyFilters, PageRange, Curriculum, CurriculumPick

        mock_filters = SurveyFilters(
            is_recognized_topic=True,
            topic_keywords=["russian", "classic"],
            page_range=PageRange(min=80, max=220),
            difficulty="high",
            language_codes=["eng"],
        )

        mock_row = MagicMock()
        mock_row.book_id = "b1"
        mock_row.title = "War and Peace"
        mock_row.author_ids = ["a1"]

        mock_curriculum = Curriculum(
            picks=[
                CurriculumPick(
                    book_id=f"b{i}",
                    title=f"Book {i}",
                    author="Tolstoy",
                    week=i,
                    reason="An essential text that anchors this part of the curriculum arc.",
                )
                for i in range(1, 6)
            ],
            overall_arc="A rigorous tour through Russian literary tradition from its classical roots.",
        )

        with patch("pipeline.extract_filters", return_value=mock_filters), \
             patch("pipeline.fetch_candidates", return_value=[mock_row] * 10), \
             patch("pipeline.generate_curriculum", return_value=mock_curriculum):
            from pipeline import generate_for_survey
            result = generate_for_survey("Russian literature", "evening read", "challenging")
            assert len(result.picks) == 5


# ---------------------------------------------------------------------------
# Test 7 — Pipeline: generate_for_survey raises on empty candidate pool
# ---------------------------------------------------------------------------
class TestPipelineEmptyPool:
    """Pipeline must raise ValueError when no books match the filters."""

    def test_empty_pool_raises_value_error(self):
        from schema import SurveyFilters, PageRange

        mock_filters = SurveyFilters(
            is_recognized_topic=True,
            topic_keywords=["obscure-topic"],
            page_range=PageRange(min=150, max=400),
            difficulty="low",
            language_codes=["eng"],
        )

        with patch("pipeline.extract_filters", return_value=mock_filters), \
             patch("pipeline.fetch_candidates", return_value=[]):
            from pipeline import generate_for_survey
            with pytest.raises(ValueError, match="No matching books"):
                generate_for_survey("obscure niche topic", "evening", "easy")


# ---------------------------------------------------------------------------
# Test 8 — FastAPI: /health and / endpoints return correct responses
# ---------------------------------------------------------------------------
class TestFastAPIEndpoints:
    """/health and / must return expected responses regardless of model state."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        # All GCP/mlflow deps are stubbed at module level above
        if "app" in sys.modules:
            del sys.modules["app"]
        import app as app_module
        return TestClient(app_module.app)

    def test_root_returns_message(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert isinstance(body["message"], str)
        assert len(body["message"]) > 0

    def test_health_returns_string(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        # Returns a plain string (model up or not)
        assert isinstance(resp.json(), str)

    def test_predict_rejects_short_query(self, client):
        resp = client.post("/predict", json={"book_query": "ab"})  # min_length=3
        assert resp.status_code == 422  # Pydantic validation error

    def test_predict_rejects_missing_field(self, client):
        resp = client.post("/predict", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 9 — extract.py: prompt injection in user input is neutralised
# ---------------------------------------------------------------------------
class TestExtractPromptInjectionGuard:
    """User-supplied fields must be capped at 500 chars before reaching Gemini.

    The extract module hard-truncates genre/time/difficulty to 500 chars.
    This test verifies that truncation is applied by inspecting what the
    mock Gemini client receives, without making a real API call.
    """

    def _make_mock_filters(self):
        from schema import SurveyFilters, PageRange
        return SurveyFilters(
            is_recognized_topic=True,
            topic_keywords=["science-fiction"],
            page_range=PageRange(min=150, max=400),
            difficulty="medium",
            language_codes=["eng"],
        )

    def test_overlong_genre_is_truncated_in_prompt(self):
        """A 2000-char genre string must not appear in the prompt verbatim."""
        giant_genre = "science fiction " * 200  # 3200 chars

        captured = {}

        mock_resp = MagicMock()
        mock_resp.parsed = self._make_mock_filters()

        def fake_generate(model, contents, config):
            captured["prompt"] = contents
            return mock_resp

        with patch("extract._client") as mock_client:
            mock_client.models.generate_content.side_effect = fake_generate
            from extract import extract_filters
            extract_filters(giant_genre, "evening read", "easy")

        assert "prompt" in captured
        # The genre is truncated to 500 chars before being placed in the prompt
        assert giant_genre not in captured["prompt"]
        assert giant_genre[:500] in captured["prompt"] or len(captured["prompt"]) < len(giant_genre)

    def test_normal_length_genre_passes_through(self):
        """A short, normal genre string should appear intact in the prompt."""
        genre = "Japanese magical realism"

        captured = {}

        mock_resp = MagicMock()
        mock_resp.parsed = self._make_mock_filters()

        def fake_generate(model, contents, config):
            captured["prompt"] = contents
            return mock_resp

        with patch("extract._client") as mock_client:
            mock_client.models.generate_content.side_effect = fake_generate
            from extract import extract_filters
            extract_filters(genre, "evening read", "moderate")

        assert genre in captured["prompt"]

    def test_returns_survey_filters_instance(self):
        """extract_filters must always return a SurveyFilters object."""
        from schema import SurveyFilters

        mock_resp = MagicMock()
        mock_resp.parsed = self._make_mock_filters()

        with patch("extract._client") as mock_client:
            mock_client.models.generate_content.return_value = mock_resp
            from extract import extract_filters
            result = extract_filters("Russian literature", "evening read", "challenging")

        assert isinstance(result, SurveyFilters)
