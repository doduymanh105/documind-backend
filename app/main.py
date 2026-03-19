from fastapi import FastAPI
from app.database import engine, Base
from app.models import models
from app.api.auth import router as auth_router
# python3 -m uvicorn app.main:app --reload
models.Base.metadata.create_all(bind = engine)

app = FastAPI(title="Documind API")

app.include_router(auth_router)

@app.get("/")
def root():
    return {"message": "Welcome to DocuMind API! Database connected successfully."}