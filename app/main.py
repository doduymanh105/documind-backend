from fastapi import FastAPI
from app.database import engine, Base
from app.models import models
from app.api.auth import router as auth_router
from app.api.document import router as document_router
from app.api.quiz import router as quiz_router
# python -m uvicorn app.main:app --reload
models.Base.metadata.create_all(bind = engine)

app = FastAPI(title="Documind API")

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(quiz_router)

@app.get("/")
def root():
    return {"message": "Welcome to DocuMind API! Database connected successfully."}
