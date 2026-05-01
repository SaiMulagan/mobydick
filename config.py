GCP_PROJECT = "molbydickproj"
GCP_REGION  = "us-central1"

BQ_DATASET  = "goodreads"
BQ_BOOKS    = f"{GCP_PROJECT}.{BQ_DATASET}.books"
BQ_AUTHORS  = f"{GCP_PROJECT}.{BQ_DATASET}.authors"

GEMINI_MODEL = "gemini-2.5-flash"