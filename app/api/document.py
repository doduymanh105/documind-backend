import os
import fitz
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from sqlalchemy import desc, or_, text

from app.database import get_db, SessionLocal
from app.models.models import User, UserDocument, Quiz, Mindmap, Essay
from app.schemas.document_schemas import DocumentListResponse,DocumentResponse

from app.services.document_service import DocumentService as service
from app.services.quiz_service import QuizService

from app.core.rag import process_text_into_knowledge_graph, generate_quiz_from_rag, generate_summary_from_rag
from app.api.auth import get_current_user

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "upload")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

router = APIRouter(prefix="/documents", tags=["Documents"])

# UPLOAD_DIR = "upload"
# os.makedirs(UPLOAD_DIR, exist_ok=True)

def extract_text_from_pdf(file_path: str) -> str:
    text=""
    try:
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print(f"Error when reading PDF : {e}")
    return text


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks = BackgroundTasks(),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user:User = Depends(get_current_user),
    
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Current system only support PDF format.")
    # xử lí file size 

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    extracted_text = extract_text_from_pdf(file_path)

    if not extracted_text.strip():
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Text not found in this PDF, Please upload appropriate File format")
    
    file_size = os.path.getsize(file_path)
    new_document = UserDocument(
        user_id= current_user.user_id,
        file_name=file.filename,
        document_url= file_path,
        size = file_size,
        summary = None
    )

    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    background_tasks.add_task(process_document_background, extracted_text, new_document.document_id)
    

    return {
        "message": "Upload and extract text successfully, AI still processing document...",
        "documemt_id": new_document.document_id,
        "file_name": file.filename,
        "text_preview": new_document.summary,
        "pdf_url": f"/documents/{new_document.document_id}/view"
    }

async def process_document_background(text: str, document_id: int):
    db = SessionLocal()
    try:
        doc = db.query(UserDocument).filter(UserDocument.document_id == document_id).first()
        if doc:
            doc.processing_status = "PROCESSING"
            db.commit()

        await process_text_into_knowledge_graph(text, document_id)

        doc = db.query(UserDocument).filter(UserDocument.document_id == document_id).first()
        if doc:
            doc.processing_status = "COMPLETED"
            db.commit()
            print(f"Document: {document_id} completed KG")
    except Exception as e:
        doc = db.query(UserDocument).filter(UserDocument.document_id == document_id).first()
        if doc:
            doc.processing_status = "FAILED"
            db.commit()
        print(f"ERROR: when processing document: {document_id}: {e}")
    finally:
        db.close()


@router.get("/{document_id}/status" , summary="Get document processing status")
async def get_document_status(document_id : int, db: Session= Depends(get_db), current_user : User = Depends(get_current_user)):
    doc = service.get_user_document(db, document_id, current_user.user_id)

    return {
        "document_id": document_id,
        "status": doc.processing_status
    }

@router.post("/{document_id}/generate-quiz")
async def generate_quiz_and_save(
    document_id: int, 
    num_questions: int = 5,
    difficulty: str = Query("MEDIUM", regex="^(EASY|MEDIUM|HARD)$"),
    db: Session = Depends(get_db),
    current_user: User= Depends(get_current_user)
    ):
    try:

        existing_document = service.get_user_document(db, document_id, current_user.user_id)

        quiz_data = await generate_quiz_from_rag(document_id, num_questions)
        
        if "error" in quiz_data:
            raise HTTPException(status_code=500, detail=quiz_data["error"])
        
        try:
            saved_quiz = QuizService.save_generated_quiz_to_db(db, quiz_data, document_id, current_user.user_id)
            
            return {
                "message": "Generate quiz successfully!",
                "quiz_id": saved_quiz.quiz_id,
                "document_id": document_id,
                "title": saved_quiz.title,
                "num_questions": len(quiz_data.get("questions", [])),
                "created_at": saved_quiz.created_at
            } 
        except Exception as e:
            print(f"SAVE ERROR: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SYSTEM ERROR: {str(e)}")
    

@router.get("/{document_id}/view", summary="View PDF document")
async def view_document(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = service.get_user_document(db, document_id, current_user.user_id)
    if not os.path.exists(doc.document_url):
        raise HTTPException(status_code=404, detail="Physical file in the system not found")
    
    file_path = os.path.abspath(doc.document_url)
    print(f"DEBUG: Server is looking for file at: {file_path}")
    
    doc.last_accessed_at = datetime.now()
    db.commit()
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, 
            detail=f"Physical file not found. Server checked: {file_path}"
        )
    
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=doc.file_name,
        content_disposition_type="inline"
    )

@router.get("/{document_id}/summarize", summary="Generate html sumary ")
async def get_document_sumary(
    document_id: int,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    doc = service.get_user_document(db, document_id, current_user.user_id)

    if doc.summary:
        print(f"Cache Hit: Retrieved summary from database for Document {document_id}")
        return {
            "message": "Summary retrieved successfully (from Database)",
            "document_id": document_id,
            "data": doc.summary,
            "is_cached": True
        }

    if hasattr(doc, 'processing_status') and doc.processing_status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Document is still processing by AI")
    
    try:
        print(f"Start generating sumary for document: {document_id}")

        clean_markdown = await generate_summary_from_rag(document_id)

        doc.summary = clean_markdown
        db.commit()
        return {
            "message": "Generate sumary successfully",
            "document_id": document_id,
            "data": clean_markdown,
            "is_cached": False
        }
    except Exception as e:
        db.rollback()
        print(f"[SUMMARY ERROR]: {e}")
        raise HTTPException(status_code=500, detail=f"Error when generate sumary: {str(e)}")
    

@router.get("/", response_model=DocumentListResponse)
async def get_all_documents(
    search: Optional[str] = None,
    file_type: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(UserDocument).filter(UserDocument.user_id== current_user.user_id)

    if search:
        query= query.filter(UserDocument.file_name.ilike(f"%{search}%"))

    if file_type and file_type.upper() != "ALL":
        query = query.filter(UserDocument.file_name.ilike(f"%.{file_type}"))

    if status and status.upper() != "ALL STATUS":
        query = query.filter(UserDocument.processing_status == status.upper())    

    total_count = query.count()

    skip = (page -1) * page_size

    documents = query.order_by(desc(UserDocument.created_at)).offset(skip).limit(page_size).all()

    result=[]
    for doc in documents:
        ext= doc.file_name.split('.')[-1].upper() if '.' in doc.file_name else 'TXT'
        
        result.append({
            "document_id": doc.document_id,
            "file_name": doc.file_name,
            "file_type": ext,
            "size": round(doc.size / (1024*1024),2) if doc.size else 0,
            "upload_date": doc.created_at,
            "last_opened": doc.last_accessed_at,
            "status": doc.processing_status,
            "category": "Software Engineering"
        })
    return{
        "total_count": total_count,
        "documents": result
    }

@router.delete("/{document_id}/delete", summary="Delete a document and its AI data")
async def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    doc = service.get_user_document(db, document_id, current_user.user_id)
    service.delete_document(db, doc)
    return {"message": "Deleted successfully"}
    

@router.get("/{document_id}/history-pro")
async def get_history(document_id: int, db: Session = Depends(get_db), current_user : User = Depends(get_current_user)):
    service.get_user_document(db, document_id, current_user.user_id)
    return service.get_history_union(db, document_id)

@router.get("/{document_id}/generated_content")
async def get_generated_content(
    document_id: int, 
    db : Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service.get_user_document(db, document_id, current_user.user_id)

    return {
        "quizzes": service.get_items_by_type(db, Quiz, document_id),
        "essays": service.get_items_by_type(db, Essay, document_id),
        "mindmaps": service.get_items_by_type(db, Mindmap, document_id),
        "recent_activity": service.get_history_union(db, document_id, limit=2)
    }
