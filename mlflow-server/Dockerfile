FROM python:3.11-slim

RUN pip install --no-cache-dir \
    mlflow==3.12.0 \
    psycopg2-binary==2.9.9 \
    google-cloud-storage==2.18.2

ENV PORT=8080

# DB_PASS, INSTANCE_CONN, ARTIFACT_BUCKET are injected at runtime by Cloud Run.
# Cloud SQL Auth Proxy mounts the socket at /cloudsql/<INSTANCE_CONN>.
CMD exec mlflow server \
  --host 0.0.0.0 \
  --port ${PORT} \
  --backend-store-uri "postgresql://mlflow:${DB_PASS}@/mlflow?host=/cloudsql/${INSTANCE_CONN}" \
  --default-artifact-root "gs://${ARTIFACT_BUCKET}" \
  --serve-artifacts
