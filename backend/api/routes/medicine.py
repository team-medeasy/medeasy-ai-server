from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional
import os
import tempfile
import shutil
import logging

# 텍스트 검색을 위한 통합 검색 로직
from backend.search.logic import search_pills
# 이미지 분석을 위한 Gemini 서비스
from backend.services.gemini_service import analyze_pill_image

router = APIRouter(prefix="/medicine", tags=["Medicine"])
logger = logging.getLogger("MedicineVisonAPI")

# 이미지 기반 검색 결과가 영 이상한 약만 가져올 때, 확실하게 사용자가 입력해서 검색할 수 있게 하기 위함...
@router.get("/text", response_model=dict) 
async def search_by_text(
    imprint: Optional[str] = Query(None, description="약품 인쇄 문자 또는 마크 코드"),
    drug_shape: Optional[str] = Query(None, description="약품 모양"),
    color_classes: Optional[str] = Query(None, description="약품 색상"),
    top_k: int = Query(8, ge=1, le=20, description="반환할 결과 수")
):
    """
    텍스트 기반 검색 API:
      - URL 쿼리 파라미터로 imprint, drug_shape, color_classes를 입력받아 통합 검색을 수행합니다.
    """
    if not imprint and not drug_shape and not color_classes:
        raise HTTPException(status_code=400, detail="최소 1개 이상의 파라미터가 필요합니다.")
    
    features = {}
    if imprint:
        features["imprint"] = imprint
    if drug_shape:
        features["drug_shape"] = drug_shape
    if color_classes:
        features["color_classes"] = color_classes

    results = await search_pills(features, top_k=top_k)
    return {
        "status": "success",
        "analysis": features,
        "results": [
            {
                "score": hit["_score"],
                "item_seq": hit["_source"].get("item_seq"),
                "data": hit["_source"]
            }
            for hit in results
        ]
    }

@router.post("/image", response_model=dict)
async def search_by_image(
    file: UploadFile = File(...),
    top_k: int = Query(5, ge=1, le=20, description="반환할 결과 수")
):
    """
    이미지 기반 검색 API:
      1. 업로드된 이미지를 임시 파일로 저장합니다.
      2. Gemini 서비스를 호출하여 이미지에서 imprint, drug_shape, color_classes 정보를 추출합니다.
      3. 추출된 정보를 기반으로 통합 검색 함수를 호출해 관련 약품을 검색합니다.
      4. 각 분석 후보에 대해 검색 결과를 묶어 반환합니다.
    """
    temp_file_path = ""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="파일 이름이 없습니다.")
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            raise HTTPException(status_code=400, detail="지원하지 않는 이미지 형식입니다. (JPG, JPEG, PNG, WEBP)")
        
        # 파일을 임시 파일로 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            temp_file_path = tmp.name
            shutil.copyfileobj(file.file, tmp)
        
        # Gemini 서비스를 통해 이미지 분석
        analysis_results = await analyze_pill_image(temp_file_path)
        if not analysis_results:
            raise HTTPException(status_code=500, detail="이미지 분석 결과가 없습니다.")
        
        formatted_results = []
        for candidate in analysis_results:
            # candidate는 {"drug_shape": ..., "color_classes": ..., "imprint": ...} 형태입니다.
            # ⬇ imprint 정제 추가
            if "imprint" in candidate and candidate["imprint"]:
                candidate["imprint"] = candidate["imprint"].replace(" ", "").replace("|", "").replace("\n", "").replace(
                    "\r", "")
            search_result = await search_pills(candidate, top_k=top_k)
            formatted_results.append({
                "analysis": candidate,
                "search_results": [
                    {
                        "score": hit["_score"],
                        "item_seq": hit["_source"].get("item_seq"),
                        "data": hit["_source"]
                    }
                    for hit in search_result
                ]
            })
        
        return {"status": "success", "results": formatted_results}
    except Exception as e:
        logger.error(f"이미지 검색 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="이미지 기반 검색 실패")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)