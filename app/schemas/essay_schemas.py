from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class EssayAttemptListResponse(BaseModel):
    attempt_id: int
    essay_id: int
    score: Optional[float]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class EssayAttemptDetailResponse(BaseModel):
    attempt_id: int
    essay_id: int
    score: Optional[float]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    
    text_answer: Optional[str]
    feedb_strength: Optional[str]
    pointforgrow: Optional[str]
    suggest_enhancemance: Optional[str]
    ai_feedback: Optional[str]

    class Config:
        from_attributes = True