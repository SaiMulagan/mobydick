#!/usr/bin/env bash
# Load the locally-extracted UCSD Goodreads files into GCS and BigQuery.
#
# Idempotent: re-running creates the bucket only if missing, and replaces
# existing tables/views cleanly.

set -euo pipefail

# ============================================================================
# CONFIG  -- edit these five values, then run ./load_to_bigquery.sh
# ============================================================================
PROJECT_ID="molbydickproj"                 # e.g. "molbydick-470101" (run: gcloud config get-value project)
DATASET="goodreads"                        # BigQuery dataset to create / reuse
LOCATION="US"                              # BigQuery + GCS location (must match)
BUCKET="gs://molbydick-goodreads-bk"    # e.g. "gs://molbydick-goodreads-bk"
FILES_DIR="."                              # directory containing the local data files
# ============================================================================

GCS_PREFIX="raw"   # objects land in $BUCKET/$GCS_PREFIX/<filename>

# ----------------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------------
echo "[preflight] checking required tools"
for cmd in gcloud bq gsutil; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: '$cmd' not found on PATH. Install the Google Cloud SDK." >&2
        exit 1
    fi
done

if [[ -z "$PROJECT_ID" || "$BUCKET" == "gs://CHANGE-ME-globally-unique" ]]; then
    echo "ERROR: edit the CONFIG block at the top of this script first." >&2
    exit 1
fi

if [[ ! -d "$FILES_DIR" ]]; then
    echo "ERROR: FILES_DIR '$FILES_DIR' does not exist." >&2
    exit 1
fi

echo "[preflight] setting active project to $PROJECT_ID"
gcloud config set project "$PROJECT_ID" >/dev/null

# ----------------------------------------------------------------------------
# Bucket setup
# ----------------------------------------------------------------------------
if gsutil ls -b "$BUCKET" >/dev/null 2>&1; then
    echo "[bucket] $BUCKET already exists, reusing"
else
    echo "[bucket] creating $BUCKET in $LOCATION"
    gsutil mb -p "$PROJECT_ID" -l "$LOCATION" "$BUCKET"
fi

# ----------------------------------------------------------------------------
# Upload local files (parallel). Skip any file that isn't on disk so the
# script remains useful for partial datasets.
# ----------------------------------------------------------------------------
LOCAL_FILES=(
    "goodreads_books.json"
    "goodreads_book_authors.json"
    "goodreads_interactions.csv"
    "book_id_map.csv"
    "user_id_map.csv"
)

UPLOAD_LIST=()
for f in "${LOCAL_FILES[@]}"; do
    if [[ -f "$FILES_DIR/$f" ]]; then
        UPLOAD_LIST+=("$FILES_DIR/$f")
    else
        echo "[upload] WARNING: $FILES_DIR/$f not found, skipping"
    fi
done

if [[ ${#UPLOAD_LIST[@]} -eq 0 ]]; then
    echo "ERROR: none of the expected files were found in $FILES_DIR" >&2
    exit 1
fi

echo "[upload] uploading ${#UPLOAD_LIST[@]} file(s) to $BUCKET/$GCS_PREFIX/ (parallel)"
gsutil -m cp "${UPLOAD_LIST[@]}" "$BUCKET/$GCS_PREFIX/"

# ----------------------------------------------------------------------------
# BigQuery dataset
# ----------------------------------------------------------------------------
DATASET_REF="$PROJECT_ID:$DATASET"
if bq --location="$LOCATION" show --dataset "$DATASET_REF" >/dev/null 2>&1; then
    echo "[dataset] $DATASET_REF already exists, reusing"
else
    echo "[dataset] creating $DATASET_REF in $LOCATION"
    bq --location="$LOCATION" mk --dataset "$DATASET_REF"
fi

# ----------------------------------------------------------------------------
# Wire-format schemas for the raw JSON files.
#
# The UCSD Goodreads JSON encodes every numeric / boolean as a quoted string
# (e.g. "num_pages": "320", "is_ebook": "false"). BigQuery's JSON loader does
# not coerce string -> number, so we must land the JSON in a STRING-typed
# staging table first and then SAFE_CAST into the canonical typed tables
# below. The staging tables are dropped at the end.
# ----------------------------------------------------------------------------
BOOKS_STAGE_SCHEMA='[
  {"name":"isbn","type":"STRING"},
  {"name":"text_reviews_count","type":"STRING"},
  {"name":"series","type":"STRING","mode":"REPEATED"},
  {"name":"country_code","type":"STRING"},
  {"name":"language_code","type":"STRING"},
  {"name":"popular_shelves","type":"RECORD","mode":"REPEATED","fields":[
    {"name":"count","type":"STRING"},
    {"name":"name","type":"STRING"}
  ]},
  {"name":"asin","type":"STRING"},
  {"name":"is_ebook","type":"STRING"},
  {"name":"average_rating","type":"STRING"},
  {"name":"kindle_asin","type":"STRING"},
  {"name":"similar_books","type":"STRING","mode":"REPEATED"},
  {"name":"description","type":"STRING"},
  {"name":"format","type":"STRING"},
  {"name":"link","type":"STRING"},
  {"name":"authors","type":"RECORD","mode":"REPEATED","fields":[
    {"name":"author_id","type":"STRING"},
    {"name":"role","type":"STRING"}
  ]},
  {"name":"publisher","type":"STRING"},
  {"name":"num_pages","type":"STRING"},
  {"name":"publication_day","type":"STRING"},
  {"name":"isbn13","type":"STRING"},
  {"name":"publication_month","type":"STRING"},
  {"name":"edition_information","type":"STRING"},
  {"name":"publication_year","type":"STRING"},
  {"name":"url","type":"STRING"},
  {"name":"image_url","type":"STRING"},
  {"name":"book_id","type":"STRING"},
  {"name":"ratings_count","type":"STRING"},
  {"name":"work_id","type":"STRING"},
  {"name":"title","type":"STRING"},
  {"name":"title_without_series","type":"STRING"}
]'

AUTHORS_STAGE_SCHEMA='[
  {"name":"author_id","type":"STRING"},
  {"name":"name","type":"STRING"},
  {"name":"average_rating","type":"STRING"},
  {"name":"text_reviews_count","type":"STRING"},
  {"name":"ratings_count","type":"STRING"}
]'

INTERACTIONS_SCHEMA='user_id:INT64,book_id:INT64,is_read:INT64,rating:INT64,is_reviewed:INT64'
BOOK_ID_MAP_SCHEMA='book_id_csv:INT64,book_id:STRING'
USER_ID_MAP_SCHEMA='user_id_csv:INT64,user_id:STRING'

# ----------------------------------------------------------------------------
# Helper: load a table from a GCS object (only if the object exists)
# ----------------------------------------------------------------------------
load_table() {
    local table="$1"        # short table name
    local source_format="$2"
    local gcs_object="$3"
    local schema_arg="$4"   # either inline "name:TYPE,..." or @file.json
    local extra_flags="${5:-}"

    if ! gsutil -q stat "$gcs_object" 2>/dev/null; then
        echo "[load] WARNING: $gcs_object not found in GCS, skipping table $table"
        return 0
    fi

    echo "[load] $table  <-  $gcs_object"
    # shellcheck disable=SC2086
    bq --location="$LOCATION" load \
        --replace \
        --source_format="$source_format" \
        $extra_flags \
        "$DATASET_REF.$table" \
        "$gcs_object" \
        "$schema_arg"
}

# Write the JSON schemas to temp files (bq load wants @file for JSON schemas)
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
echo "$BOOKS_STAGE_SCHEMA"   > "$TMP_DIR/books.schema.json"
echo "$AUTHORS_STAGE_SCHEMA" > "$TMP_DIR/authors.schema.json"

# ----------------------------------------------------------------------------
# Loads
#
# JSON sources land in _stage_* tables (all STRING); the canonical typed
# `books` and `authors` tables are built from them further below.
# ----------------------------------------------------------------------------
load_table "_stage_books" \
    "NEWLINE_DELIMITED_JSON" \
    "$BUCKET/$GCS_PREFIX/goodreads_books.json" \
    "$TMP_DIR/books.schema.json" \
    "--max_bad_records=100 --ignore_unknown_values"

load_table "_stage_authors" \
    "NEWLINE_DELIMITED_JSON" \
    "$BUCKET/$GCS_PREFIX/goodreads_book_authors.json" \
    "$TMP_DIR/authors.schema.json" \
    "--max_bad_records=100 --ignore_unknown_values"

load_table "interactions" \
    "CSV" \
    "$BUCKET/$GCS_PREFIX/goodreads_interactions.csv" \
    "$INTERACTIONS_SCHEMA" \
    "--skip_leading_rows=1"

load_table "book_id_map" \
    "CSV" \
    "$BUCKET/$GCS_PREFIX/book_id_map.csv" \
    "$BOOK_ID_MAP_SCHEMA" \
    "--skip_leading_rows=1"

load_table "user_id_map" \
    "CSV" \
    "$BUCKET/$GCS_PREFIX/user_id_map.csv" \
    "$USER_ID_MAP_SCHEMA" \
    "--skip_leading_rows=1"

# ----------------------------------------------------------------------------
# Build the canonical typed tables from the staging tables.
#
# SAFE_CAST turns empty strings / malformed values into NULL instead of
# failing the whole query. After this step the staging tables and the legacy
# v_books / v_authors views (from earlier versions of this script) are
# dropped so there is exactly one source of truth per entity.
# ----------------------------------------------------------------------------
echo "[table] creating typed $DATASET.books"
bq --location="$LOCATION" query --use_legacy_sql=false --quiet \
    "CREATE OR REPLACE TABLE \`$PROJECT_ID.$DATASET.books\` AS
     SELECT
       book_id,
       work_id,
       title,
       title_without_series,
       description,
       language_code,
       country_code,
       publisher,
       format,
       edition_information,
       isbn,
       isbn13,
       asin,
       kindle_asin,
       url,
       link,
       image_url,
       authors,
       series,
       similar_books,
       ARRAY(
         SELECT AS STRUCT
           SAFE_CAST(s.count AS INT64) AS count,
           s.name
         FROM UNNEST(popular_shelves) AS s
       ) AS popular_shelves,
       SAFE_CAST(average_rating     AS FLOAT64) AS average_rating,
       SAFE_CAST(ratings_count      AS INT64)   AS ratings_count,
       SAFE_CAST(text_reviews_count AS INT64)   AS text_reviews_count,
       SAFE_CAST(num_pages          AS INT64)   AS num_pages,
       SAFE_CAST(publication_year   AS INT64)   AS publication_year,
       SAFE_CAST(publication_month  AS INT64)   AS publication_month,
       SAFE_CAST(publication_day    AS INT64)   AS publication_day,
       SAFE_CAST(LOWER(is_ebook)    AS BOOL)    AS is_ebook
     FROM \`$PROJECT_ID.$DATASET._stage_books\`"

echo "[table] creating typed $DATASET.authors"
bq --location="$LOCATION" query --use_legacy_sql=false --quiet \
    "CREATE OR REPLACE TABLE \`$PROJECT_ID.$DATASET.authors\` AS
     SELECT
       author_id,
       name,
       SAFE_CAST(average_rating     AS FLOAT64) AS average_rating,
       SAFE_CAST(ratings_count      AS INT64)   AS ratings_count,
       SAFE_CAST(text_reviews_count AS INT64)   AS text_reviews_count
     FROM \`$PROJECT_ID.$DATASET._stage_authors\`"

# ----------------------------------------------------------------------------
# Clean up: drop staging tables and any legacy v_* views from prior runs.
# ----------------------------------------------------------------------------
echo "[cleanup] dropping staging tables and legacy views"
bq --location="$LOCATION" query --use_legacy_sql=false --quiet \
    "DROP TABLE IF EXISTS \`$PROJECT_ID.$DATASET._stage_books\`;
     DROP TABLE IF EXISTS \`$PROJECT_ID.$DATASET._stage_authors\`;
     DROP VIEW  IF EXISTS \`$PROJECT_ID.$DATASET.v_books\`;
     DROP VIEW  IF EXISTS \`$PROJECT_ID.$DATASET.v_authors\`;"

echo
echo "Done."
echo "  GCS:       $BUCKET/$GCS_PREFIX/"
echo "  BigQuery:  $PROJECT_ID:$DATASET  (typed tables: books, authors,"
echo "             interactions, book_id_map, user_id_map)"
