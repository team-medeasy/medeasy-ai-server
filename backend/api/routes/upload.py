# backend/api/routes/upload.py
from fastapi import APIRouter, HTTPException, UploadFile, File
import json
import logging
from backend.db.crud import add_pill

router = APIRouter(prefix="/upload", tags=["Upload"])
logger = logging.getLogger("UploadAPI")

@router.post("/json", response_model=dict)
async def upload_json(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        pills = json.loads(contents)
        if not isinstance(pills, list):
            raise HTTPException(status_code=400, detail="Invalid JSON format. Expected a list.")
        
        inserted_count = 0
        failed_items = []
        for pill in pills:
            pill_id = await add_pill(pill)
            if pill_id:
                inserted_count += 1
            else:
                failed_items.append(pill)
        
        return {
            "message": f"{inserted_count} pills added successfully",
            "failed_items": failed_items
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file format")
    except Exception as e:
        logger.error(f"❌ JSON 파일 업로드 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
