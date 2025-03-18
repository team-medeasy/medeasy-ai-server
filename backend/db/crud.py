# backend/db/crud.py
import logging
from typing import Optional, Dict, Any

from backend.db.mongodb import db  # mongodb.py에서 생성한 db 객체
from backend.db.elastic import es, INDEX_NAME
from backend.utils.helpers import parse_color_classes, parse_mark_code
from backend.db.elastic import process_pill_data  # process_pill_data: ES 인덱싱 전 데이터 전처리 함수 (아래 참고)

logger = logging.getLogger(__name__)

async def add_pill(pill_data: Dict[str, Any]) -> Optional[str]:
    """
    약품 정보를 MongoDB와 Elasticsearch에 추가합니다.
    1. Pydantic 모델 혹은 JSON 데이터를 받아서 필요한 필드 정규화 수행.
    2. MongoDB에 저장 후, MongoDB ObjectID를 반환.
    3. Elasticsearch에는 색상/모양 그룹 등 추가 전처리 후 인덱싱.
    """
    try:
        # 데이터 전처리 (이미 Pydantic 모델에서 변환되었다면, 중복 처리는 피할 수 있음)
        pill_data["color_classes"] = parse_color_classes(pill_data.get("color_classes", ""))
        pill_data["mark_code_front_anal"] = parse_mark_code(pill_data.get("mark_code_front_anal", ""))
        pill_data["mark_code_back_anal"] = parse_mark_code(pill_data.get("mark_code_back_anal", ""))

        item_seq = pill_data.get("item_seq")
        if not item_seq:
            logger.error("❌ item_seq가 없는 데이터입니다.")
            return None

        # MongoDB 저장
        result = await db.pills.insert_one(pill_data)
        mongo_id = str(result.inserted_id)

        # Elasticsearch 전처리: process_pill_data() 함수를 사용해 색상/모양 그룹 등 추가
        es_data = process_pill_data(pill_data)
        await es.index(index=INDEX_NAME, id=item_seq, document=es_data)

        return mongo_id
    except Exception as e:
        logger.error(f"❌ 약품 추가 실패: {e}", exc_info=True)
        return None

async def get_pill(pill_id: str) -> Optional[Dict[str, Any]]:
    """MongoDB에서 pill_id로 약품 정보를 조회합니다."""
    try:
        pill = await db.pills.find_one({"_id": pill_id})
        if pill:
            pill["_id"] = str(pill["_id"])
        return pill
    except Exception as e:
        logger.error(f"❌ 약품 조회 실패: {e}")
        return None

async def update_pill(pill_id: str, update_data: Dict[str, Any]) -> bool:
    """
    약품 정보를 수정합니다.
    MongoDB 업데이트 후, Elasticsearch에도 변경 내용을 반영합니다.
    """
    try:
        pill = await db.pills.find_one({"_id": pill_id})
        if not pill:
            return False

        item_seq = pill.get("item_seq")
        if not item_seq:
            logger.error("❌ 약품에 item_seq가 없습니다.")
            return False

        # 필요시 update_data 전처리
        if "color_classes" in update_data:
            update_data["color_classes"] = parse_color_classes(update_data["color_classes"])
        if "mark_code_front_anal" in update_data:
            update_data["mark_code_front_anal"] = parse_mark_code(update_data["mark_code_front_anal"])
        if "mark_code_back_anal" in update_data:
            update_data["mark_code_back_anal"] = parse_mark_code(update_data["mark_code_back_anal"])

        result = await db.pills.update_one({"_id": pill_id}, {"$set": update_data})
        if result.matched_count == 0:
            return False

        # Elasticsearch 업데이트: 업데이트 데이터를 ES 전처리 로직으로 보완
        es_update_data = update_data.copy()
        if "_id" in es_update_data:
            del es_update_data["_id"]
        await es.update(index=INDEX_NAME, id=item_seq, doc=es_update_data)
        return True
    except Exception as e:
        logger.error(f"❌ 약품 수정 실패: {e}")
        return False

async def delete_pill(pill_id: str) -> bool:
    """MongoDB와 Elasticsearch에서 약품을 삭제합니다."""
    try:
        pill = await db.pills.find_one({"_id": pill_id})
        if not pill:
            return False

        item_seq = pill.get("item_seq")
        if not item_seq:
            logger.error("❌ 약품에 item_seq가 없습니다.")
            return False

        result = await db.pills.delete_one({"_id": pill_id})
        if result.deleted_count == 0:
            return False

        await es.delete(index=INDEX_NAME, id=item_seq, ignore=[404])
        return True
    except Exception as e:
        logger.error(f"❌ 약품 삭제 실패: {e}")
        return False
