"""
FastAPI inference server for the Moby Dicks book recommender.

Loads the model from the MLflow registry when MLFLOW_TRACKING_URI is set,
otherwise (or on failure) falls back to the self-contained local copy that
train.py writes into ./model_artifacts/book_recommender. This keeps the
container functional even if the tracking server is unreachable.
"""

import logging
import os
from pathlib import Path

import mlflow.pyfunc
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("moby.app")
logging.basicConfig(level=logging.INFO)

# Cloud Run-hosted MLflow tracking server. Set MLFLOW_TRACKING_URI in the
# runtime environment to point at the deployed service URL.
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "https://mlflow-server-493581728016.us-central1.run.app",
)
MODEL_URI = os.getenv("MODEL_URI", "models:/BookRecommender/Production")
LOCAL_MODEL_PATH = os.getenv(
    "LOCAL_MODEL_PATH",
    str(Path(__file__).resolve().parent / "model_artifacts" / "book_recommender"),
)

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

app = FastAPI(
    title="Moby Dick",
    description="Give users book recommendations.",
    version="0.1",
)

model = None


def _load_model():
    """Try the MLflow registry first; fall back to the bundled local copy."""
    global model
    try:
        model = mlflow.pyfunc.load_model(MODEL_URI)
        logger.info("Loaded model from registry: %s", MODEL_URI)
        return
    except Exception as exc:
        logger.warning("Registry load failed (%s); using local copy.", exc)
    try:
        model = mlflow.pyfunc.load_model(LOCAL_MODEL_PATH)
        logger.info("Loaded model from local path: %s", LOCAL_MODEL_PATH)
    except Exception as exc:
        logger.error("Local model load failed (%s); /predict will return 503.", exc)
        model = None


@app.on_event("startup")
def load_model_on_startup():
    _load_model()


class request_body(BaseModel):
    book_query: str = Field(..., min_length=3, max_length=1000)


class response_body(BaseModel):
    book_query: str
    predictions: list


@app.get("/")
def main():
    return {"message": "This is our model for recommending books"}


@app.get("/health")
def health_check():
    return "Model exists and is up" if model is not None else "Model is not up"


@app.post("/predict", response_model=response_body)
def predict(data: request_body):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    X = pd.DataFrame({"query": [data.book_query]})
    raw = model.predict(X)
    # pyfunc returns one prediction per input row; we always send a single row.
    predictions = raw[0] if isinstance(raw, list) and raw else []
    return response_body(book_query=data.book_query, predictions=predictions)
