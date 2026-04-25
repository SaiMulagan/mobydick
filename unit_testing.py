import mlflow.pyfunc
from fastapi import FastAPI
from pydantic import BaseModel, Field

def test_health_check():
    