GCP_PROJECT = "molbydickproj"
GCP_REGION  = "us-central1"

BQ_DATASET  = "goodreads"
BQ_BOOKS    = f"{GCP_PROJECT}.{BQ_DATASET}.books"
BQ_AUTHORS  = f"{GCP_PROJECT}.{BQ_DATASET}.authors"

GEMINI_MODEL      = "gemini-2.5-flash"
# Lite model for cheap/short tasks like keyword extraction — same JSON
# discipline, ~0.5–1s faster than the regular flash model on small prompts.
GEMINI_MODEL_FAST = "gemini-2.5-flash-lite"