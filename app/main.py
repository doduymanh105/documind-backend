from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.models import models
from app.api.auth import router as auth_router
from app.api.document import router as document_router
from app.api.quiz import router as quiz_router
from app.api.essay import router as essay_router
from app.api.mindmap import router as mindmap_router
import torch
import torch.nn as nn
import sys
from fastapi.middleware.cors import CORSMiddleware
setattr(sys.modules['torch'], 'nn', nn)
# python -m uvicorn app.main:app --reload
models.Base.metadata.create_all(bind = engine)

app = FastAPI(title="Documind API")

origins = [    
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://ten-mien-cua-sep.com", 
    "*"                        
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],           
    allow_headers=["*"],           
)
app.include_router(auth_router)
app.include_router(document_router)
app.include_router(quiz_router)
app.include_router(essay_router)
app.include_router(mindmap_router)
app.mount("/upload", StaticFiles(directory="upload"), name="upload")

@app.get("/")
def root():
    return {"message": "Welcome to DocuMind API! Database connected successfully."}
