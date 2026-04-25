from schema import SurveyFilters

raw = {
    "topic_keywords": ["russian", "russia", "russian-literature"],
    "era": {"start": 1700, "end": 1799},
    "page_range": {"min": 80, "max": 220},
    "difficulty": "high",
    "language_codes": ["eng"],
}
print(SurveyFilters.model_validate(raw))

# Should raise: era.start > era.end
try:
    SurveyFilters.model_validate({**raw, "era": {"start": 1900, "end": 1700}})
except Exception as e:
    print(f"validation correctly rejected bad era: {e}")