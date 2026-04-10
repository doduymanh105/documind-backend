import os
import fitz
from sqlalchemy.orm import Session
from sqlalchemy import desc, text
from datetime import datetime
from fastapi import HTTPException

from app.models.models import UserDocument, Quiz, Essay, Mindmap
from app.core.rag import process_text_into_knowledge_graph, generate_summary_from_rag, generate_quiz_from_rag

class DocumentService:
    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        text = ""
        try:
            with fitz.open(file_path) as doc:
                for page in doc:
                    text += page.get_text()
        except Exception as e:
            print(f"Error reading PDF: {e}")
        return text

    @staticmethod
    def get_user_document(db: Session, document_id: int, user_id: int):
        doc = db.query(UserDocument).filter(UserDocument.document_id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        if doc.user_id != user_id:
            raise HTTPException(status_code=403, detail="Permission denied")
        return doc

    @staticmethod
    def get_history_union(db: Session, document_id: int, limit: int = None):
        limit_query = f"LIMIT {limit}" if limit else ""
        
        query = text(f"""
            SELECT 
                'QUIZ' as type, 
                title as name,   -- Giả sử bảng quizzes có cột quiz_title
                created_at, 
                'COMPLETED' as status, 
                q.quiz_id as id 
            FROM quizzes q 
            WHERE document_id = :doc_id
            
            UNION ALL
            
            SELECT 
                'ESSAY' as type, 
                essay_title as name,  -- Giả sử bảng essays có cột essay_title
                created_at, 
                'COMPLETED' as status, 
                e.essay_id as id 
            FROM essays e 
            WHERE document_id = :doc_id
            
            UNION ALL
            
            SELECT 
                'MINDMAP' as type, 
                title as name,        -- Giả sử bảng mindmaps có cột title
                created_at, 
                'COMPLETED' as status, 
                m.mindmap_id as id 
            FROM mindmaps m 
            WHERE document_id = :doc_id
            
            ORDER BY created_at DESC
            {limit_query}
        """)
    
        result = db.execute(query, {"doc_id": document_id}).fetchall()
        return [dict(row._mapping) for row in result]

    @staticmethod
    def delete_document(db: Session, doc: UserDocument):
        file_path = doc.document_url
        try:
            db.delete(doc)
            db.commit()
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception as e:
            db.rollback()
            raise e
        
    @staticmethod
    def get_items_by_type(db: Session, model, document_id: int):
        items = db.query(model).filter(model.document_id == document_id).all()
        return {
            "count": len(items),
            "items": items
        }