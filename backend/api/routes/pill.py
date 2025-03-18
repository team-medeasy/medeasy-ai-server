# backend/api/routes/pill.py
from fastapi import APIRouter, HTTPException
from backend.api.models.pill import PillCreate, PillResponse
from backend.db.crud import add_pill, get_pill, update_pill, delete_pill
from typing import Dict, Any
import logging

router = APIRouter(prefix="/pill", tags=["Pill"])
logger = logging.getLogger("PillAPI")

@router.get("/{pill_id}", response_model=PillResponse)
async def get_pill_info(pill_id: str):
    pill = await get_pill(pill_id)
    if not pill:
        raise HTTPException(status_code=404, detail="Pill not found")
    return pill

@router.post("/add/", response_model=Dict[str, Any])
async def add_pill_api(pill: PillCreate):
    pill_data = pill.dict()
    pill_id = await add_pill(pill_data)
    if not pill_id:
        raise HTTPException(status_code=500, detail="Failed to add pill")
    return {"message": "Pill added successfully", "pill_id": pill_id}

@router.put("/update/{pill_id}", response_model=Dict[str, Any])
async def update_pill_api(pill_id: str, update_data: Dict[str, Any]):
    success = await update_pill(pill_id, update_data)
    if not success:
        raise HTTPException(status_code=404, detail="Pill not found or update failed")
    return {"message": "Pill updated successfully"}

@router.delete("/delete/{pill_id}", response_model=Dict[str, Any])
async def delete_pill_api(pill_id: str):
    success = await delete_pill(pill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Pill not found or delete failed")
    return {"message": "Pill deleted successfully"}
