from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from typing import List, Optional
from app.models.models import Quiz, User, UserDocument, QuizAttempt
from app.schemas.quiz_schemas import QuizDetailResponse, QuizSubmitResponse, QuizSubmitRequest, QuizAttemptResponse
from app.api.auth import get_current_user
from app.database import get_db
from app.services.quiz_service import QuizService
from app.models import models


router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


@router.get("/", summary="get all quizzes group by document ")
def get_quizzes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    file_type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
):
    query = db.query(UserDocument).filter(UserDocument.user_id== current_user.user_id)

    if search:
        query= query.filter(UserDocument.file_name.ilike(f"%{search}%"))

    if file_type and file_type.upper() != "ALL":
        query = query.filter(UserDocument.file_name.ilike(f"%.{file_type}"))

    if status and status.upper() != "ALL STATUS":
        query = query.filter(UserDocument.processing_status == status.upper())
        
    total_document_count= query.count()
    skip = (page -1) * page_size

    # optimize in future Quiz table : number_questions
    document=  query.options(
        joinedload(UserDocument.quizzes).joinedload(Quiz.questions)
    ).order_by(UserDocument.created_at.desc()).offset(skip).limit(page_size).all()

    result_items=[]
    for doc in document:
        ext = doc.file_name.split('.')[-1].upper() if '.' in doc.file_name else 'PDF'

        quizzes_data = []

        sorted_quizzes = sorted(doc.quizzes, key=lambda x: x.quiz_id)
        for q in sorted_quizzes:
            q_count = len(q.questions) if hasattr(q, 'questions') else 0
            quizzes_data.append({
                "quiz_id": q.quiz_id,
                "title": q.title,
                "status": "Completed" if q.max_grade > 0 else "Processing",
                "score": q.max_grade,
                "num_questions": q_count,
                "difficulty": q.difficulty if hasattr(q, 'difficulty') else 'MEDIUM',
                "last_opened": q.updated_at,
                "created_at": q.created_at
            })
        
        result_items.append({
            "document_id": doc.document_id,
            "file_name": doc.file_name,
            "file_type": ext,
            "created_at": doc.created_at,
            "quiz_count": len(doc.quizzes),
            "quizzes": quizzes_data
        })

    return {
        "total_count": total_document_count,
        "page": page,
        "page_size": page_size,
        "items": result_items
    }
    



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


@router.delete("/{quiz_id}", summary="Delete quiz by id")
def delete_quiz_by_id(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quiz = db.query(Quiz).filter(
        Quiz.quiz_id == quiz_id, 
        Quiz.is_deleted == False
    ).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if quiz.creator_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You have no permission to access this quiz")
    
    quiz.is_deleted = True
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred during deletion")
    
    return {
        "status": "success",
        "message": f"Quiz {quiz_id} has been deleted successfully",
        "quiz_id": quiz_id
    }


@router.get("/{quiz_id}/attempts", summary="get attempt of taking quiz", response_model=QuizAttemptResponse)
def get_quiz_attempts(
    quiz_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    quiz = quiz_validate(quiz_id, db,current_user)
    attempts = db.query(QuizAttempt).filter(QuizAttempt.quiz_id == quiz_id).order_by(QuizAttempt.completed_at.desc()).all()
    return {
        "attempt_count": len(attempts),
        "attempts" : attempts
    }


@router.get("/{quiz_id}/attempts/{attempt_id}")
def get_quiz_attempt_detail(
    quiz_id: int,
    attempt_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    attempt = db.query(models.QuizAttempt).options(
        joinedload(models.QuizAttempt.quiz)
    ).filter(
        models.QuizAttempt.attempt_id == attempt_id,
        models.QuizAttempt.quiz_id == quiz_id,
        models.QuizAttempt.user_id == current_user.user_id
    ).first()

    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    user_answers = db.query(models.UserAnswer).filter(
        models.UserAnswer.attempt_id == attempt_id
    ).all()

    detailed_answers = []
    for ua in user_answers:
        question = db.query(models.Question).options(
            joinedload(models.Question.options)
        ).filter(models.Question.question_id == ua.question_id).first()

        if question:
            correct_opt = next((o for o in question.options if o.is_correct), None)

            detailed_answers.append({
                "question_id": question.question_id,
                "question_content": question.content,
                "question_type": question.question_type,
                "selected_option_id": ua.selected_option_id,
                "is_correct": ua.selected_option_id == correct_opt.option_id if correct_opt else False,
                "options": [
                    {
                        "option_id": o.option_id,
                        "content": o.content,
                        "is_correct": o.is_correct
                    } for o in question.options
                ]
            })
    return {
        "attempt_id": attempt.attempt_id,
        "quiz_title": attempt.quiz.title if attempt.quiz else "Quiz",
        "score": attempt.score,
        "status": attempt.status,
        "answers": detailed_answers
    }



    

def quiz_validate(quiz_id: int, db: Session,current_user: User):

    quiz = db.query(Quiz).filter(Quiz.quiz_id==quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    if quiz.document and quiz.document.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You don't have permission to access this quiz")
    return quiz
