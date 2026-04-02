from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class DocumentResponse(BaseModel):
    document_id: int
    file_name: str
    file_type: str
    size: float
    upload_date: datetime
    last_opened: Optional[datetime]
    status: str
    category: Optional[str]="General"
    
    class Config:
        from_attribute = True
    
class DocumentListResponse(BaseModel):
    total_count: int
    documents: List[DocumentResponse]
