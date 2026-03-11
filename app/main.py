from fastapi import FastAPI
from app.database import engine, Base
from app.models import models

models.Base.metadata.create_all(bind = engine)

app = FastAPI(title="Documind API")

@app.get("/")
def root():
    return {"message": "Welcome to DocuMind API! Database connected successfully."}