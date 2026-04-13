from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.api.auth import get_current_user
from app.models import models
import json
import re
from app.core.rag import generate_single_essay_question
from app.core.rag import get_rag_engine, evaluate_essay_submission
from app.core.rag import QueryParam 
from datetime import datetime
from app.models.models import User
from app.schemas.essay_schemas import EssayAttemptListResponse, EssayAttemptDetailResponse
from typing import List

router = APIRouter(
    prefix="/essays",
    tags=["Essays"]
)

@router.post("/generate/{document_id}")
async def create_essay(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
    ):

    doc = db.query(models.UserDocument).filter(
        models.UserDocument.document_id == document_id,
        models.UserDocument.user_id == current_user.user_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    essay_data = await generate_single_essay_question(document_id)
    
    if not essay_data:
        raise HTTPException(status_code=500, detail="AI failed to generate essay content")

    new_essay = models.Essay(
        document_id=document_id,
        essay_title=essay_data.get('essay_title'),
        quick_explanation=essay_data.get('quick_explanation'),
        essay_content=essay_data.get('essay_content'),
        max_grade=essay_data.get('max_grade', 0.0)
    )
    
    db.add(new_essay)
    db.commit()
    db.refresh(new_essay)
    
    return {
        "status": "success",
        "essay_id": new_essay.essay_id,
        "title": new_essay.essay_title
    }

@router.get("/list-by-documents")
def get_essays_overview(
    db: Session = Depends(get_db),
    current_user : User = Depends(get_current_user)
    ):
   

    docs = (
        db.query(models.UserDocument)
        .filter(
            models.UserDocument.user_id == current_user.user_id,
            models.UserDocument.essays.any()
        )
        .options(selectinload(models.UserDocument.essays)) # "Hốt" luôn essay về trong 1 nốt nhạc
        .all()
    )    
    result = []
    for doc in docs:
        
        essay_previews = []
        for essay in doc.essays:
            essay_previews.append({
                "essay_id": essay.essay_id,
                "essay_title": essay.essay_title,
                "full_content": essay.essay_content,
                "created_at": essay.created_at,
                "max_grade": essay.max_grade
            })
            
        result.append({
            "document_id": doc.document_id,
            "file_name": doc.file_name,
            "essay_count": len(essay_previews),
            "essays": essay_previews
        })
        
    return result

@router.get("/{essay_id}")
def get_essay_detail(
    essay_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
    ):
    essay = db.query(models.Essay).join(models.UserDocument).filter(
        models.Essay.essay_id == essay_id,
        models.UserDocument.user_id == current_user.user_id
    ).first()
    if not essay:
        raise HTTPException(status_code=404, detail="Essay not found")
    
    return {
        "essay_id": essay.essay_id,
        "title": essay.essay_title,
        "quick_explanation": essay.quick_explanation,
        "essay_content": essay.essay_content,
        "max_grade": essay.max_grade,
        "document_name": essay.document.file_name
    }
def to_markdown_list(data):
    if isinstance(data, list):
        return "\n".join([f"- {item}" for item in data])
    return str(data) if data else ""

@router.post("/{essay_id}/submit")
async def submit_essay(
    essay_id: int, 
    current_user: User = Depends(get_current_user),
    text_answer: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    essay = db.query(models.Essay).filter(models.Essay.essay_id == essay_id).first()
    if not essay:
        raise HTTPException(status_code=404, detail="Essay not found")
   
    rag_engine = get_rag_engine(essay.document_id)
    await rag_engine.initialize_storages()
    
    context = await rag_engine.aquery(
        essay.essay_content, 
        param=QueryParam(mode="naive", only_need_context=True)
    )

    eval_res = await evaluate_essay_submission(
        essay_question=essay.essay_content,
        user_answer=text_answer,
        context=context
    )

    if not eval_res:
        raise HTTPException(status_code=500, detail="AI Grading failed")

   
   
    attempt = models.QuizAttempt(
        user_id=current_user.user_id,
        essay_id=essay_id,
        score=eval_res['score'],
        status='COMPLETED',
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )
    db.add(attempt)
    db.flush()

    new_essay_answer = models.UserEssayAnswer(
        attempt_id=attempt.attempt_id,
        essay_id=essay_id,
        text_answer=text_answer,
        score_obtained=eval_res.get('score'),
        feedb_strength=to_markdown_list(eval_res.get('strengths')),
        pointforgrow=to_markdown_list(eval_res.get('growth_points')),
        suggest_enhancemance=to_markdown_list(eval_res.get('enhancement'))
    )
    
    new_score = eval_res['score']
    if new_score > (essay.max_grade or 0):
        essay.max_grade = new_score

    db.add(new_essay_answer)
    db.commit()

    return {
        "status": "COMPLETED",
        "score": new_score,
        "feedback": {
            "strengths": eval_res['strengths'],
            "points_for_growth": eval_res['growth_points'],
            "enhancement": eval_res['enhancement']
        }
    }


@router.get("/{essay_id}/attempts", response_model=List[EssayAttemptListResponse])
def get_essay_attempts (
    essay_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    essay_exists = db.query(models.Essay).filter(models.Essay.essay_id == essay_id).first()
    if not essay_exists:
        raise HTTPException(status_code=404, detail="Essay not found")
    
    attempts = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.essay_id == essay_id,
        models.QuizAttempt.user_id == current_user.user_id
    ).order_by(models.QuizAttempt.started_at.desc()).all()

    return attempts


@router.get("/{essay_id}/attempts/{attempt_id}", response_model=EssayAttemptDetailResponse)
def get_essay_attempt_detail (
    essay_id: int,
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    essay_exists = db.query(models.Essay).filter(models.Essay.essay_id == essay_id).first()
    if not essay_exists:
        raise HTTPException(status_code=404, detail="Essay not found")

    attempt = db.query(models.QuizAttempt).filter(
        models.QuizAttempt.attempt_id == attempt_id,
        models.QuizAttempt.user_id == current_user.user_id
        ).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    answer = db.query(models.UserEssayAnswer).filter(
        models.UserEssayAnswer.attempt_id == attempt_id
    ).first()

    return {
        "attempt_id": attempt.attempt_id,
        "essay_id": attempt.essay_id,
        "score": attempt.score,
        "status": attempt.status,
        "started_at": attempt.started_at,
        "completed_at": attempt.completed_at,
        "text_answer": answer.text_answer if answer else None,
        "feedb_strength": answer.feedb_strength if answer else None,
        "pointforgrow": answer.pointforgrow if answer else None,
        "suggest_enhancemance": answer.suggest_enhancemance if answer else None,
        "ai_feedback": answer.ai_feedback if answer else None
    }


    
