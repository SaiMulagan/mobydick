FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app
 
# Copy and install requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all Python files and dependencies
COPY * .

# FastAPI Expose
EXPOSE 8000

# MlFlow Expose
EXPOSE 5000

RUN mlflow server --backend-store-uri sqlite:///mlflow/mlflow.db --default-artifact-root /mlflow/artifacts --host 0.0.0.0 --port 5000

# Run FastAPI using the correct environment name from environment.yml
CMD ["conda", "run", "--no-capture-output", "-n", "moby", "fastapi", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
