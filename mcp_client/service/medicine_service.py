import tempfile
import os
import logging
from typing import Dict, Any, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from backend.search.logic import search_pills, search_medicine_by_item_seq
from backend.services.gemini_service import analyze_pill_image

logger = logging.getLogger(__name__)

medeasy_api_url=os.getenv("MEDEASY_API_URL", "https://api.medeasy.dev")

async def process_pill_image(image_data: bytes) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    알약 이미지를 처리하고 분석하는 함수

    Args:
        image_data: 이미지 바이너리 데이터

    Returns:
        Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
            - 분석 결과 데이터 (빈 리스트일 수 있음)
            - 성공 메시지 (성공 시)
            - 에러 메시지 (실패 시)
    """
    temp_file_path = None
    medicines_found: List[Dict[str, Any]] = []

    try:
        # 임시 파일로 이미지 저장
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(image_data)
            logger.info(f"이미지 임시 파일 저장: {temp_file_path}")

        # 이미지 분석 함수 호출
        logger.info("약품 이미지 분석 시작...")
        pill_results = await analyze_pill_image(temp_file_path)
        if not pill_results:
            return [], "사진을 분석할 수 없습니다. 다시 시도해 주세요."

        logger.info(f"약품 이미지 분석 결과: {pill_results}")

        # 모든 약품 결과를 처리
        for pill_result in pill_results:
            search_result = await search_pills(pill_result, 5)

            # 검색 결과가 없는 경우 다음 약품으로
            if not search_result:
                continue

            # 검색된 약품 정보 처리
            for hit in search_result:
                item_seq = hit["_source"].get("item_seq")
                if not item_seq:
                    continue

                try:
                    # item_seq로 의약품 데이터 찾기
                    medicine_data = await search_medicine_by_item_seq(item_seq)

                    # 결과가 이미 리스트에 있는지 확인 (중복 방지)
                    if medicine_data and not any(med.get("item_seq") == item_seq for med in medicines_found):
                        # 필요한 정보만 추출하여 저장
                        medicine_info = {
                            "item_seq": item_seq,
                            "item_name": medicine_data.get("item_name", "알 수 없음"),
                            "entp_name": medicine_data.get("entp_name", "알 수 없음"),
                            "chart": medicine_data.get("chart", "알 수 없음"),
                            "drug_shape": medicine_data.get("drug_shape", "알 수 없음"),
                            "color_classes": medicine_data.get("color_classes", "알 수 없음"),
                            "line_front": medicine_data.get("line_front", ""),
                            "line_back": medicine_data.get("line_back", ""),
                            "print_front": medicine_data.get("print_front", ""),
                            "print_back": medicine_data.get("print_back", ""),
                            "class_name": medicine_data.get("class_name", "알 수 없음"),
                            "indications": medicine_data.get("indications", "정보 없음"),  # 효능
                            "dosage": medicine_data.get("dosage", "정보 없음"),  # 용법
                            "precautions": medicine_data.get("precautions", "정보 없음"),  # 주의사항
                            "side_effects" : medicine_data.get("side_effects", "정보 없음"),
                            "image_url": medicine_data.get("item_image", "")
                        }
                        medicines_found.append(medicine_info)
                except Exception as e:
                    logger.error(f"의약품 정보 처리 중 오류: {str(e)}")
                    continue

        # 결과에 따른 응답 메시지 생성
        if not medicines_found:
            return [], "사진에서 의약품을 식별할 수 없습니다. 다른 사진을 시도해 주세요."

        logger.info( f"사진에서 {len(medicines_found)}개의 의약품을 식별했습니다.")

        return medicines_found, None

    except Exception as e:
        logger.exception(f"알약 이미지 처리 중 오류 발생: {str(e)}")
        return [], f"이미지 처리 중 오류가 발생했습니다"

    finally:
        # 임시 파일 삭제
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.info(f"임시 파일 삭제: {temp_file_path}")
            except Exception as e:
                logger.error(f"임시 파일 삭제 실패: {str(e)}")


def format_medicine_search_results(medicines: List[Dict[str, Any]]) -> str:
    """
    의약품 검색 결과를 정형화된 메시지 형식으로 변환합니다.

    Args:
        medicines: 의약품 정보 리스트

    Returns:
        정형화된 검색 결과 메시지
    """
    if not medicines:
        return "검색된 의약품이 없습니다. 다른 사진으로 다시 시도해 주세요."

    # 헤더 메시지
    lines = ["의약품 사진 검색 결과입니다."]

    # # 각 의약품 정보 추가
    # for idx, med in enumerate(medicines, 1):
    #     class_name = med.get("class_name", "")
    #     item_name = med.get("item_name", "")
    #     drug_shape = med.get("drug_shape", "")
    #     chart = med.get("chart", "")
    #
    #     # 마크 정보 구성
    #     mark_info = []
    #     front_print = med.get("print_front", "")
    #     back_print = med.get("print_back", "")
    #
    #     if front_print:
    #         mark_info.append(f"앞면 '{front_print}'")
    #     if back_print and back_print != front_print:
    #         mark_info.append(f"뒷면 '{back_print}'")
    #
    #     mark_text = ", ".join(mark_info) if mark_info else ""
    #
    #     # 의약품 정보 한 줄로 구성
    #     med_info = f"{idx}. {class_name}, {item_name}, {drug_shape}, {chart}, {mark_text}"
    #     lines.append(med_info)
    #
    # # 질문 추가
    # lines.append("")  # 빈 줄 추가
    lines.append("이중 찾으시는 의약품이 있으신가요?")
    lines.append("의약품 정보를 자세히 알려드리거나, 복용 일정을 등록해드릴게요!")

    return "\n".join(lines)


async def search_medicines_by_name(
        jwt_token: str,
        medicine_name: str
):
    api_url = f"{medeasy_api_url}/medicine/search"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    params = {"name": medicine_name}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            medicines = response.json().get("body", [])

            if not medicines:
                return None

            # 첫 번째 검색 결과 사용 (가장 관련성 높은 결과로 가정)
            return medicines
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"약 검색 중 오류: {str(e)}")

async def find_medicine_by_id(
        jwt_token: str,
        medicine_id: str
):
    api_url = f"{medeasy_api_url}/medicine/medicine_id/{medicine_id}"
    headers = {"Authorization": f"Bearer {jwt_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()
            medicine = response.json().get("body", [])

            if not medicine:
                return None

            return medicine
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"약 검색 중 오류: {str(e)}")