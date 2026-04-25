from extract import extract_filters
from candidates import fetch_candidates
from curriculum import generate_curriculum
from schema import Curriculum

POOL_SIZE = 25  # cost cap; tunable per cost analysis

def generate_for_survey(genre, time_to_read, difficulty):
    filters = extract_filters(genre, time_to_read, difficulty)
    if not filters.is_recognized_topic:
        raise ValueError(
            "We couldn't recognize that as a topic. Try something specific "
            "like 'Russian literature' or 'popular astrophysics'."
        )
    rows = fetch_candidates(filters)
    pool = rows[:POOL_SIZE]
    if not pool:
        raise ValueError(
            "No matching books were found in the catalog. "
            "Try a broader genre or different keywords."
        )
    return generate_curriculum(genre, time_to_read, difficulty, pool)