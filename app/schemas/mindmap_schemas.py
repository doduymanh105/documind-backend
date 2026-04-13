from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any, List

class MindmapResponse(BaseModel):
    mindmap_id: int
    document_id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True

class MindmapDetail(MindmapResponse):
    structure_json: Dict[str, Any]


class MindmapUpdate(BaseModel):
    title: Optional[str] = None
    structure_json: Dict[str, Any]