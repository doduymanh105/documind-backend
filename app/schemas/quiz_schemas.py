from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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