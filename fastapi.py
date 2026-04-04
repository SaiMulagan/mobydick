import mlflow.pyfunc
from fastapi import FastAPI
from pydantic import BaseModel

mlflow_uri = "http://34.134.157.206:5000"
model_uri = "models:/BookRecommender/Production"
mlflow.set_tracking_uri(mlflow_uri)

app = FastAPI(
    title="Moby Dick",
    description="Give users book recommendations.",
    version="0.1",
)

model = None

@app.on_event("startup")
def load_model():
    global model
    #model = mlflow.pyfunc.load_model(model_uri)         We don't have a model yet


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
    X = [data.book_query]
    predictions = model.predict(X)
    return response_body(book_query=data.book_query, predictions=predictions.tolist())
