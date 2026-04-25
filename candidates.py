from google.cloud import bigquery
from google.cloud.bigquery import ScalarQueryParameter, ArrayQueryParameter

from config import GCP_PROJECT, BQ_BOOKS
from schema import SurveyFilters

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
      b.book_id, b.title, b.description, b.num_pages, b.publication_year,
      b.average_rating, b.ratings_count, b.language_code,
      ARRAY(
        SELECT s.name FROM UNNEST(b.popular_shelves) s, noise n
        WHERE SAFE_CAST(s.count AS INT64) >= 20
          AND LOWER(s.name) NOT IN UNNEST(n.shelves)
        ORDER BY SAFE_CAST(s.count AS INT64) DESC LIMIT 10
      ) AS top_shelves,
      ARRAY(SELECT a.author_id FROM UNNEST(b.authors) a) AS author_ids,
      (
        SELECT COUNT(DISTINCT LOWER(k))
        FROM UNNEST(b.popular_shelves) s, noise n, UNNEST(@keywords) k
        WHERE SAFE_CAST(s.count AS INT64) >= 20
          AND LOWER(s.name) NOT IN UNNEST(n.shelves)
          AND LOWER(k) IN UNNEST(SPLIT(LOWER(s.name), '-'))
      ) AS match_score
    FROM `{BQ_BOOKS}` b
    WHERE b.language_code IN UNNEST(@langs)
      AND b.num_pages BETWEEN @page_min AND @page_max
      AND b.ratings_count >= 100
    QUALIFY ROW_NUMBER() OVER (PARTITION BY b.work_id ORDER BY b.ratings_count DESC) = 1
  )
SELECT * FROM scored
WHERE match_score >= 1
ORDER BY match_score DESC, ratings_count DESC
LIMIT 200
"""

_client = bigquery.Client(project=GCP_PROJECT)


def fetch_candidates(filters: SurveyFilters) -> list[bigquery.Row]:
    job_config = bigquery.QueryJobConfig(query_parameters=[
        ArrayQueryParameter("keywords",  "STRING", filters.topic_keywords),
        ArrayQueryParameter("langs",     "STRING", filters.language_codes),
        ScalarQueryParameter("page_min", "INT64", filters.page_range.min),
        ScalarQueryParameter("page_max", "INT64", filters.page_range.max),
        ScalarQueryParameter("era_start","INT64",
                             filters.era.start if filters.era else None),
        ScalarQueryParameter("era_end",  "INT64",
                             filters.era.end if filters.era else None),
    ])
    return list(_client.query(_SQL, job_config=job_config).result())