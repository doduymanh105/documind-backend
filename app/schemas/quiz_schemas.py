from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.schemas.document_schemas import DocumentResponse

class OptionDisplay(BaseModel):
    option_id: int
    content: str

    class Config:
        from_attributes = True

class QuestionDisplay(BaseModel):
    question_id: int
    content: str
    question_type: str
    options: List[OptionDisplay]

    class Config:
        from_attributes = True

class QuizDetailResponse(BaseModel):
    quiz_id: int
    title: str
    description: Optional[str]
    difficulty : str
    estimated_time: Optional[int]
    questions: List[QuestionDisplay]

    class Config:
        from_attributes: True



class AnswerSubmit(BaseModel):
    question_id: int
    selected_option_id: int

class QuizSubmitRequest(BaseModel):
    answers: List[AnswerSubmit]

class AnswerResultResponse(BaseModel):
    question_id: int
    is_correct: bool
    user_selected_option_id: Optional[int] = None
    correct_option_id: int
    explanation: Optional[str]

class QuizSubmitResponse(BaseModel):
    attempt_id: int
    score: float
    total_questions: int
    correct_answers: int
    result: List[AnswerResultResponse]


class QuizItemResponse(BaseModel):
    quiz_id: int
    title: str
    status: str = "Completed"
    score: Optional[float] = 0.0 
    num_questions: int 
    last_opened: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentWithQuizzes(BaseModel):
    document_id: int
    file_name: str
    file_type: str
    created_at: datetime
    quiz_count: int
    quizzes: List[QuizItemResponse]


class PaginatedQuizListResponse(BaseModel):
    total_count: int
    page: int
    page_size: int
    items: List[DocumentWithQuizzes]
