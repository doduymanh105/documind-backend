from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy.orm import Session, selectinload
from app.database import get_db
from app.api.auth import get_current_user
from app.models import models
from app.core.rag import generate_mindmap_from_rag
import json
from app.schemas import mindmap_schemas as schemas
from sqlalchemy import desc


router = APIRouter(
    prefix="/mindmaps",
    tags=["Mindmaps"]
)

@router.get("/list-by-documents")
def get_mindmaps_grouped_by_documents(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    documents = db.query(models.UserDocument).options(
        selectinload(models.UserDocument.mindmaps)
    ).filter(models.UserDocument.user_id == current_user.user_id
             ).order_by( desc(models.UserDocument.created_at)
              ).all()

    result = []
    for doc in documents:
        result.append({
            "document_id": doc.document_id,
            "file_name": doc.file_name,
            "mindmap_count": len(doc.mindmaps),
            "mindmaps": [
                {
                    "mindmap_id": m.mindmap_id,
                    "title": m.title,
                    "created_at": m.created_at
                } for m in doc.mindmaps
            ]
        })    
    return result

@router.post("/{document_id}/mindmap", response_model=schemas.MindmapResponse)
async def create_mindmap_api(
    document_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    mindmap_data = await generate_mindmap_from_rag(document_id)
    
    if not mindmap_data:
        raise HTTPException(status_code=500, detail="AI can not generate mindmap now.")

    new_mindmap = models.Mindmap(
        document_id=document_id,
        title=mindmap_data.get("name", "New Mindmap"),
        structure_json=json.dumps(mindmap_data)
    )
    
    db.add(new_mindmap)
    db.commit()
    db.refresh(new_mindmap)
    
    return {
        "mindmap_id": new_mindmap.mindmap_id,
        "document_id": new_mindmap.document_id,
        "title": new_mindmap.title,
        "created_at": new_mindmap.created_at

    }

@router.get("/{mindmap_id}", response_model=schemas.MindmapDetail)
def get_mindmap_detail(
    mindmap_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    mindmap = db.query(models.Mindmap).filter(models.Mindmap.mindmap_id == mindmap_id).first()
    
    if not mindmap:
        raise HTTPException(status_code=404, detail="Mindmap not found")
    
    return {
        "mindmap_id": mindmap.mindmap_id,
        "document_id": mindmap.document_id,
        "title": mindmap.title,
        "created_at": mindmap.created_at,
        "structure_json": json.loads(mindmap.structure_json)
    }


@router.put("/{mindmap_id}", response_model=schemas.MindmapDetail)
def update_mindmap(
    mindmap_id: int,
    update_data: schemas.MindmapUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    mindmap = db.query(models.Mindmap).join(models.UserDocument).filter(
        models.Mindmap.mindmap_id == mindmap_id,
        models.UserDocument.user_id == current_user.user_id
    ).first()
    if not mindmap:
        raise HTTPException(status_code=404, detail="Mindmap not found or access denied")

    if update_data.title:
        mindmap.title = update_data.title
    

    mindmap.structure_json = json.dumps(update_data.structure_json, ensure_ascii=False)

    db.commit()
    db.refresh(mindmap)

    return {
        "mindmap_id": mindmap.mindmap_id,
        "title": mindmap.title,
        "document_id": mindmap.document_id,
        "created_at": mindmap.created_at,
        "structure_json": update_data.structure_json 
    }


@router.delete("/{mindmap_id}", status_code=status.HTTP_200_OK)
def delete_mindmap(
    mindmap_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
   
    mindmap = db.query(models.Mindmap).join(models.UserDocument).filter(
        models.Mindmap.mindmap_id == mindmap_id,
        models.UserDocument.user_id == current_user.user_id
    ).first()

    if not mindmap:
        raise HTTPException(
            status_code=404, 
            detail="Mindmap not found or not have permission to delete!"
        )

    try:
        db.delete(mindmap)
        db.commit()
        
        return {
            "message": f"Delete mindmap successfully: '{mindmap.title}'!",
            "mindmap_id": mindmap_id
        }
    except Exception as e:
        db.rollback()
        print(f"[DELETE ERROR]: {e}")
        raise HTTPException(status_code=500, detail="Error when deleting mindmap.")
    