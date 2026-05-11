"""
Trains the Phase-2 book recommender and registers it with MLflow.

Environment variables:
    MLFLOW_TRACKING_URI  Tracking server. Defaults to a local SQLite store
                         so the script runs offline. Set to the Cloud Run
                         MLflow URL in production
                         (e.g. https://mlflow-server-XYZ-uc.a.run.app).
    MLFLOW_EXPERIMENT    Experiment name. Defaults to "book-recommender".

The script:
    1. Builds a TF-IDF cosine-similarity recommender over a curated corpus.
    2. Evaluates retrieval quality with hold-one-shelf-out Precision@5.
    3. Logs params + metrics + artifacts to MLflow and registers the model
       as "BookRecommender", promoting the new version to "Production".
    4. Saves a self-contained copy to ./model_artifacts/book_recommender/
       so the Docker image does not depend on the tracking server at runtime.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import joblib
import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


REPO_ROOT = Path(__file__).resolve().parent
# Pinned to the Cloud Run MLflow server in molbydickproj. Override with
# MLFLOW_TRACKING_URI=sqlite:///... for fully offline runs.
DEFAULT_TRACKING_URI = "https://mlflow-server-493581728016.us-central1.run.app"
TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT", "book-recommender")
MODEL_NAME = "BookRecommender"
LOCAL_MODEL_DIR = REPO_ROOT / "model_artifacts" / "book_recommender"

BOOKS = [
    {"book_id": "b1",  "title": "Crime and Punishment",            "author": "Dostoyevsky",
     "shelves": "russian-literature classics philosophy psychology dark"},
    {"book_id": "b2",  "title": "The Brothers Karamazov",          "author": "Dostoyevsky",
     "shelves": "russian-literature classics philosophy theology family"},
    {"book_id": "b3",  "title": "War and Peace",                   "author": "Tolstoy",
     "shelves": "russian-literature classics historical-fiction war epic"},
    {"book_id": "b4",  "title": "Anna Karenina",                   "author": "Tolstoy",
     "shelves": "russian-literature classics romance tragedy society"},
    {"book_id": "b5",  "title": "Norwegian Wood",                  "author": "Murakami",
     "shelves": "japanese-literature contemporary romance melancholy coming-of-age"},
    {"book_id": "b6",  "title": "Kafka on the Shore",              "author": "Murakami",
     "shelves": "japanese-literature magical-realism contemporary surreal"},
    {"book_id": "b7",  "title": "The Wind-Up Bird Chronicle",      "author": "Murakami",
     "shelves": "japanese-literature magical-realism contemporary"},
    {"book_id": "b8",  "title": "One Hundred Years of Solitude",   "author": "Garcia Marquez",
     "shelves": "magical-realism classics latin-american-literature family"},
    {"book_id": "b9",  "title": "A Brief History of Time",         "author": "Hawking",
     "shelves": "popular-science physics cosmology astrophysics"},
    {"book_id": "b10", "title": "Cosmos",                          "author": "Sagan",
     "shelves": "popular-science astronomy astrophysics philosophy"},
    {"book_id": "b11", "title": "Sapiens",                         "author": "Harari",
     "shelves": "popular-science history anthropology evolution"},
    {"book_id": "b12", "title": "The Selfish Gene",                "author": "Dawkins",
     "shelves": "popular-science biology evolution genetics"},
    {"book_id": "b13", "title": "Meditations",                     "author": "Marcus Aurelius",
     "shelves": "philosophy stoicism ancient-rome classics ethics"},
    {"book_id": "b14", "title": "The Republic",                    "author": "Plato",
     "shelves": "philosophy ancient-greek classics political-philosophy"},
    {"book_id": "b15", "title": "Beyond Good and Evil",            "author": "Nietzsche",
     "shelves": "philosophy german-philosophy ethics 19th-century"},
    {"book_id": "b16", "title": "Dune",                            "author": "Herbert",
     "shelves": "science-fiction space-opera politics ecology epic"},
    {"book_id": "b17", "title": "Neuromancer",                     "author": "Gibson",
     "shelves": "science-fiction cyberpunk technology noir"},
    {"book_id": "b18", "title": "Foundation",                      "author": "Asimov",
     "shelves": "science-fiction classics space-opera politics"},
    {"book_id": "b19", "title": "The Left Hand of Darkness",       "author": "Le Guin",
     "shelves": "science-fiction feminist anthropology gender"},
    {"book_id": "b20", "title": "Pride and Prejudice",             "author": "Austen",
     "shelves": "classics romance british-literature 19th-century"},
    {"book_id": "b21", "title": "Jane Eyre",                       "author": "Bronte",
     "shelves": "classics romance gothic british-literature 19th-century"},
    {"book_id": "b22", "title": "Wuthering Heights",               "author": "Bronte",
     "shelves": "classics romance gothic british-literature tragedy"},
    {"book_id": "b23", "title": "Beloved",                         "author": "Morrison",
     "shelves": "contemporary literary-fiction american-literature slavery"},
    {"book_id": "b24", "title": "Invisible Man",                   "author": "Ellison",
     "shelves": "classics american-literature race identity"},
    {"book_id": "b25", "title": "The Old Man and the Sea",         "author": "Hemingway",
     "shelves": "classics american-literature short novella"},
    {"book_id": "b26", "title": "Moby Dick",                       "author": "Melville",
     "shelves": "classics american-literature sea epic 19th-century"},
    {"book_id": "b27", "title": "Walden",                          "author": "Thoreau",
     "shelves": "classics american-literature nature philosophy 19th-century"},
    {"book_id": "b28", "title": "Hyperion",                        "author": "Simmons",
     "shelves": "science-fiction space-opera epic"},
    {"book_id": "b29", "title": "Project Hail Mary",               "author": "Weir",
     "shelves": "science-fiction contemporary space hard-sf"},
    {"book_id": "b30", "title": "The Master and Margarita",        "author": "Bulgakov",
     "shelves": "russian-literature classics magical-realism satire"},
]


class BookRecommender(mlflow.pyfunc.PythonModel):
    """TF-IDF cosine-similarity recommender. Maps a free-text query
    ("russian classics", "popular astrophysics", ...) to the top-k matching
    books from the corpus."""

    TOP_K = 5

    def load_context(self, context):
        self.vectorizer = joblib.load(context.artifacts["vectorizer"])
        self.book_vectors = joblib.load(context.artifacts["book_vectors"])
        with open(context.artifacts["books"], "r") as f:
            self.books = json.load(f)

    def _recommend(self, query: str):
        qv = self.vectorizer.transform([query])
        scores = cosine_similarity(qv, self.book_vectors).flatten()
        top_idx = np.argsort(-scores)[: self.TOP_K]
        return [
            {
                "book_id": self.books[i]["book_id"],
                "title":   self.books[i]["title"],
                "author":  self.books[i]["author"],
                "score":   float(scores[i]),
            }
            for i in top_idx
        ]

    def predict(self, context, model_input, params=None):
        if isinstance(model_input, pd.DataFrame):
            queries = model_input.iloc[:, 0].astype(str).tolist()
        elif isinstance(model_input, (list, tuple, np.ndarray)):
            queries = [str(x) for x in model_input]
        else:
            queries = [str(model_input)]
        return [self._recommend(q) for q in queries]


def _precision_at_5(vectorizer, book_vectors, books) -> float:
    """Hold one shelf-token out of each book's query and check whether the
    book still ranks in the top-5. Returns mean Precision@5 over the corpus."""
    rng = np.random.default_rng(0)
    hits = 0
    for i, b in enumerate(books):
        tokens = b["shelves"].split()
        if len(tokens) < 2:
            continue
        chosen = rng.choice(tokens, size=len(tokens) - 1, replace=False)
        qv = vectorizer.transform([" ".join(chosen)])
        scores = cosine_similarity(qv, book_vectors).flatten()
        if i in np.argsort(-scores)[:5]:
            hits += 1
    return hits / len(books)


def main():
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)
    print(f"MLflow tracking URI: {TRACKING_URI}")
    print(f"Experiment: {EXPERIMENT_NAME}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        vectorizer_path = tmp / "vectorizer.joblib"
        vectors_path    = tmp / "book_vectors.joblib"
        books_path      = tmp / "books.json"

        vectorizer = TfidfVectorizer(
            token_pattern=r"[a-zA-Z0-9\-]+",
            lowercase=True,
            ngram_range=(1, 1),
            min_df=1,
        )
        corpus = [f"{b['title']} {b['author']} {b['shelves']}" for b in BOOKS]
        book_vectors = vectorizer.fit_transform(corpus)

        joblib.dump(vectorizer, vectorizer_path)
        joblib.dump(book_vectors, vectors_path)
        with open(books_path, "w") as f:
            json.dump(BOOKS, f)

        p_at_5 = _precision_at_5(vectorizer, book_vectors, BOOKS)
        print(f"Precision@5 (hold-one-out): {p_at_5:.3f}")

        artifacts = {
            "vectorizer":   str(vectorizer_path),
            "book_vectors": str(vectors_path),
            "books":        str(books_path),
        }
        pip_reqs = ["scikit-learn", "joblib", "pandas", "numpy"]

        with mlflow.start_run() as run:
            mlflow.log_param("corpus_size", len(BOOKS))
            mlflow.log_param("vectorizer", "tfidf")
            mlflow.log_param("ngram_range", "1-1")
            mlflow.log_param("top_k", BookRecommender.TOP_K)
            mlflow.log_metric("precision_at_5", p_at_5)
            mlflow.log_metric("vocab_size", len(vectorizer.vocabulary_))

            mlflow.pyfunc.log_model(
                artifact_path="model",
                python_model=BookRecommender(),
                artifacts=artifacts,
                input_example=pd.DataFrame({"query": ["russian classics"]}),
                pip_requirements=pip_reqs,
                registered_model_name=MODEL_NAME,
            )
            print(f"Logged run: {run.info.run_id}")

        client = MlflowClient()
        latest = client.get_latest_versions(MODEL_NAME, stages=["None"])
        if latest:
            client.transition_model_version_stage(
                name=MODEL_NAME,
                version=latest[0].version,
                stage="Production",
                archive_existing_versions=True,
            )
            print(f"Promoted {MODEL_NAME} v{latest[0].version} -> Production")

        if LOCAL_MODEL_DIR.exists():
            shutil.rmtree(LOCAL_MODEL_DIR)
        LOCAL_MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
        mlflow.pyfunc.save_model(
            path=str(LOCAL_MODEL_DIR),
            python_model=BookRecommender(),
            artifacts=artifacts,
            pip_requirements=pip_reqs,
        )
        print(f"Saved local copy: {LOCAL_MODEL_DIR}")


if __name__ == "__main__":
    main()
