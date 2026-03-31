import os
import fitz
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models.models import User, UserDocument



from app.services.quiz_service import save_generated_quiz_to_db
from app.core.rag import process_text_into_knowledge_graph, generate_quiz_from_rag
from app.api.auth import get_current_user

router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = "upload"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
        summary = extracted_text[:200] +  "..." if len(extracted_text) > 200 else extracted_text
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
        # thay bằng preview sau khi xử lí AI
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
async def get_document_status(document_id : int, db: Session= Depends(get_db)):
    doc = db.query(UserDocument).filter(UserDocument.document_id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found!")
        
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

        existing_document = db.query(UserDocument).filter(UserDocument.document_id== document_id).first()
        if not existing_document:
            raise HTTPException(status_code=404, detail="Document not found!")
        if existing_document.user_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="You do not have permission to access this document!")
        
    
        quiz_data = await generate_quiz_from_rag(document_id, num_questions)
        
        if "error" in quiz_data:
            raise HTTPException(status_code=500, detail=quiz_data["error"])
        
        try:
            saved_quiz = save_generated_quiz_to_db(db, quiz_data, document_id, current_user.user_id)

            
            return {
                "message": "Generate quiz successfully!",
                "document_id": document_id,
                "data": quiz_data
            } 
        except Exception as e:
            raise HTTPException(status_code=500, detail=quiz_data["error"])

    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SYSTEM ERROR: {str(e)}")
    

@router.get("{/document_id}/view", summary="View PDF document")
async def view_document(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(UserDocument).filter(UserDocument.document_id== document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.document_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You have no permission to access this document")
    if not os.path.exists(doc.document_url):
        raise HTTPException(status_code=404, detail="Physical file in the system not found")
    
    return FileResponse(
        path = doc.document_url,
        media_type="application/pdf",
        filename=doc.file_name,
    )

@router.get("/{document_id}/summarize", summary="Generate html sumary ")
async def getDocumentSumary(
    document_id: int,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    doc = db.query(UserDocument).filter(UserDocument.document_id == document_id).first()
    if not doc or doc.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Invalid document or no permission to access")
    
    
