FROM python:3.11-slim

WORKDIR /app

# Build deps for scientific Python wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY app.py train.py ./

# Train + register the model and bake the self-contained pyfunc copy into
# the image. Uses a local SQLite tracking store at build time; override by
# passing --build-arg MLFLOW_TRACKING_URI=... to log to a remote server.
ARG MLFLOW_TRACKING_URI=""
ENV MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI}
RUN python train.py

# Default to the local model copy at runtime so the container does not need
# to reach the tracking server to serve predictions. Override MODEL_URI to
# pull from the registry instead.
ENV LOCAL_MODEL_PATH=/app/model_artifacts/book_recommender
ENV MODEL_URI=""

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
