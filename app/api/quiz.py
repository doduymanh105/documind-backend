from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.models.models import Quiz, User
from app.schemas.quiz_schemas import QuizDetailResponse, QuizSubmitResponse, QuizSubmitRequest
from app.api.auth import get_current_user
from app.database import get_db
from app.services.quiz_service import QuizService


router = APIRouter(prefix="/quizzes", tags=["Quizzes"])

@router.get("/{quiz_id}", response_model=QuizDetailResponse)
def get_quiz_for_taking(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quiz = QuizService.get_quiz_detail(db, quiz_id)

    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    if quiz.document and quiz.document.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You don't have permission to access this quiz")
    
    return quiz

@router.post("/{quiz_id}/submit", response_model=QuizSubmitResponse)
def submit_quiz(
    quiz_id: int,
    submission: QuizSubmitRequest,
    db: Session = Depends(get_db),
    current_user : User = Depends(get_current_user)
):
    quiz = QuizService.get_quiz_detail(db, quiz_id)
    if not quiz or (quiz.document and quiz.document.user_id != current_user.user_id):
        raise HTTPException(status_code=403, detail="Permission denied")
    
    result = QuizService.submit_quiz_logic(db, quiz_id, current_user.user_id, submission)

    if not result:
        raise HTTPException(status_code=400, detail="Error during submission")

    return result