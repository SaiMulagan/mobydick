from google.cloud import bigquery
from google.cloud.bigquery import ScalarQueryParameter, ArrayQueryParameter

from config import GCP_PROJECT, BQ_BOOKS, BQ_DATASET
from schema import SurveyFilters

# Reddit signal view built by sub-step 1d (see v_reddit_signal definition).
_BQ_REDDIT_SIGNAL = f"{GCP_PROJECT}.{BQ_DATASET}.v_reddit_signal"

_SQL = f"""
WITH
  noise AS (
    SELECT [
      'to-read','currently-reading','favorites','default','owned','library',
      'books-i-own','my-books','reading','re-read','read','wishlist',
      'want-to-read','wish-list','english','kindle','audiobook','audiobooks',
      'ebook','ebooks','book-club','dnf','abandoned'
    ] AS shelves
  ),
  scored AS (
    SELECT
      b.book_id, b.work_id, b.title, b.description, b.num_pages, b.publication_year,
      b.average_rating, b.ratings_count, b.language_code,
      ARRAY(
        SELECT s.name FROM UNNEST(b.popular_shelves) s, noise n
        WHERE s.count >= 20
          AND LOWER(s.name) NOT IN UNNEST(n.shelves)
        ORDER BY s.count DESC LIMIT 10
      ) AS top_shelves,
      ARRAY(SELECT a.author_id FROM UNNEST(b.authors) a) AS author_ids,
      (
        SELECT COUNT(DISTINCT LOWER(k))
        FROM UNNEST(b.popular_shelves) s, noise n, UNNEST(@keywords) k
        WHERE s.count >= 20
          AND LOWER(s.name) NOT IN UNNEST(n.shelves)
          AND LOWER(k) IN UNNEST(SPLIT(LOWER(s.name), '-'))
      ) AS match_score
    FROM `{BQ_BOOKS}` b
    WHERE b.language_code IN UNNEST(@langs)
      AND b.num_pages BETWEEN @page_min AND @page_max
      AND b.ratings_count >= 100
      -- Filter out user-supplied already-read titles. Strip leading
      -- "The ", "A ", "An " on both sides so that "Brothers Karamazov"
      -- typed by a user matches the canonical "The Brothers Karamazov".
      AND REGEXP_REPLACE(LOWER(b.title), r'^(the |a |an )', '') NOT IN (
        SELECT REGEXP_REPLACE(LOWER(t), r'^(the |a |an )', '')
        FROM UNNEST(@exclude_titles) t
      )
      AND REGEXP_REPLACE(LOWER(b.title_without_series), r'^(the |a |an )', '') NOT IN (
        SELECT REGEXP_REPLACE(LOWER(t), r'^(the |a |an )', '')
        FROM UNNEST(@exclude_titles) t
      )
    QUALIFY ROW_NUMBER() OVER (PARTITION BY b.work_id ORDER BY b.ratings_count DESC) = 1
  ),
  with_reddit AS (
    SELECT
      s.*,
      COALESCE(rs.recommended_count,    0) AS reddit_recommended,
      COALESCE(rs.asked_similar_count,  0) AS reddit_asked_similar,
      COALESCE(rs.weighted_score,       0) AS reddit_weighted_score
    FROM scored s
    LEFT JOIN `{_BQ_REDDIT_SIGNAL}` rs USING (work_id)
  )
SELECT * FROM with_reddit
WHERE match_score >= 1
ORDER BY
  match_score DESC,
  reddit_recommended DESC,
  reddit_weighted_score DESC,
  ratings_count DESC
LIMIT 200
"""

_client = bigquery.Client(project=GCP_PROJECT)


def fetch_candidates(
    filters: SurveyFilters,
    exclude_titles: list[str] | None = None,
) -> list[bigquery.Row]:
    """Run the parameterized candidate query.

    `exclude_titles` is a list of free-text titles the user has already read.
    They're filtered out of the pool via case-insensitive title match against
    both `title` and `title_without_series`. Empty list = no filtering.
    """
    exclude_titles = exclude_titles or []
    job_config = bigquery.QueryJobConfig(query_parameters=[
        ArrayQueryParameter("keywords",       "STRING", filters.topic_keywords),
        ArrayQueryParameter("langs",          "STRING", filters.language_codes),
        ArrayQueryParameter("exclude_titles", "STRING", exclude_titles),
        ScalarQueryParameter("page_min", "INT64", filters.page_range.min),
        ScalarQueryParameter("page_max", "INT64", filters.page_range.max),
        ScalarQueryParameter("era_start","INT64",
                             filters.era.start if filters.era else None),
        ScalarQueryParameter("era_end",  "INT64",
                             filters.era.end if filters.era else None),
    ])
    return list(_client.query(_SQL, job_config=job_config).result())