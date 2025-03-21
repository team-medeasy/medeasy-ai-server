# backend/services/gemini_service.py

import os
import json
import logging
import io
import re
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from PIL import Image
from google.cloud import aiplatform
from vertexai.preview.generative_models import GenerativeModel, Part, SafetySetting, HarmCategory, HarmBlockThreshold
from vertexai.generative_models import GenerationConfig
from dotenv import load_dotenv

logger = logging.getLogger("gemini_service")

# 환경변수 로드 (.env 또는 도커 환경에서 주입)
load_dotenv()

# Vertex AI 초기화
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
if not PROJECT_ID:
    logger.warning("⚠️ GOOGLE_CLOUD_PROJECT 환경변수가 설정되지 않았습니다.")

try:
    location = "us-central1"  # 또는 다른 리전
    aiplatform.init(project=PROJECT_ID, location=location)
    logger.info("✅ Vertex AI 초기화 완료")
except Exception as e:
    logger.error(f"❌ Vertex AI 초기화 오류: {e}")

model_name = "gemini-1.5-flash-002"
try:
    model = GenerativeModel(model_name)
    logger.info(f"✅ Gemini 모델 '{model_name}' 로드 완료")
except Exception as e:
    logger.error(f"❌ Gemini 모델 로드 오류: {e}")
    model = None

async def analyze_pill_image(image_path: str) -> List[Dict[str, Any]]:
    """
    이미지 파일 경로를 받아 Gemini API를 통해 약품의 식별 특성을 분석합니다.
    Gemini에는 반드시 아래 정보만을 반환하도록 요청합니다:
      - "drug_shape": 약품의 모양 (예: 원형, 타원형, 장방형, 반원형, 삼각형, 사각형, 마름모형, 오각형, 육각형, 팔각형, 기타)
      - "color_classes": 약품의 색상 정보 (단일 색상은 문자열, 캡슐형(두 가지 색상)인 경우 리스트)
      - "imprint": 약품에 인쇄된 텍스트, 숫자, 기호 등을 정확히 추출 (영어 대소문자 구분 포함), 분할선이 있는 경우 '|'로 구분
    만약 이미지 내에 여러 후보가 존재한다면, JSON 배열 형태로 반환하십시오.
    (참고: '마크'라는 단어에 대한 처리는 이후 데이터베이스 로직에서 imprint를 기반으로 print와 mark 코드 4개 필드에 매핑됩니다.)
    """
    try:
        with Image.open(image_path) as img:
            img_byte_arr = io.BytesIO()
            img_format = img.format if img.format else "JPEG"
            img.save(img_byte_arr, format=img_format)
            img_bytes = img_byte_arr.getvalue()
        
        # 프롬프트: 반드시 필요한 3가지 필드만 반환하도록 요청합니다.
        prompt = (
            "다음 의약품 이미지에서 정확한 식별 정보를 JSON 형식으로 반환해주세요.\n"
            "반드시 아래 키들을 포함해야 합니다:\n"
            "  - \"drug_shape\": 약품의 모양을 [원형, 타원형, 장방형, 반원형, 삼각형, 사각형, 마름모형, "
            "오각형, 육각형, 팔각형, 기타] 중 하나로 정확히 분류\n"
            "  - \"color_classes\": 약품의 색상 정보를 추출 (단일 색상은 문자열, 캡슐형(두 가지 색상)인 경우 리스트로 반환)\n"
            "    (색상은 다음 중으로 반환, 예: 하양, 노랑, 주황, 분홍, 빨강, 갈색, 연두, 초록, 청록, 파랑, 남색, 자주, 보라, 회색, 검정, 투명)\n"
            "  - \"imprint\": 의약품에 인쇄된 텍스트, 숫자, 기호 등을 정확히 추출 (영어 대소문자 구분 포함)\n"
            "예시 반환: {\"drug_shape\": \"원형\", \"color_classes\": \"하양\", \"imprint\": \"A+\"}\n"
            "여러 약품이 있다면 JSON 배열 형식으로 반환하십시오."
        )
        
        logger.info("🔄 Gemini API 호출 중...")
        
        image_part = Part.from_data(mime_type=f"image/{img_format.lower()}", data=img_bytes)
        prompt_part = Part.from_text(prompt)
        
        generation_config = GenerationConfig(temperature=0.1, max_output_tokens=4096)
        safety_settings = [
            SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_NONE),
            SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_NONE)
        ]
        
        response = model.generate_content(
            [prompt_part, image_part],
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        if not response.text:
            raise HTTPException(status_code=422, detail="사진에서 의약품이 발견되지 않았습니다.")

        json_data = _extract_json_from_response(response.text)

        if isinstance(json_data, dict) and not json_data:
            raise HTTPException(status_code=422, detail="사진에서 의약품이 발견되지 않았습니다.")
        elif isinstance(json_data, list) and len(json_data) == 0:
            raise HTTPException(status_code=422, detail="사진에서 의약품이 발견되지 않았습니다.")
        elif not isinstance(json_data, (dict, list)):
            raise ValueError("Gemini API 응답 형식이 예상과 다릅니다.")

        return [json_data] if isinstance(json_data, dict) else json_data

    except HTTPException:
        raise  # 위에서 명시적으로 발생시킨 에러는 그대로 전달
    except Exception as e:
        logger.error(f"❌ 이미지 분석 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="이미지 분석 중 오류가 발생했습니다.")

def _extract_json_from_response(response_text: str) -> Any:
    """
    Gemini 응답 텍스트에서 JSON 데이터를 추출합니다.
    코드 블록 형태든 전체 텍스트 중 JSON 객체이든 상관없이 추출합니다.
    """
    try:
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r"({[\s\S]*})", response_text)
            if json_match:
                json_str = json_match.group(1)
            else:
                raise ValueError("응답에서 JSON 데이터를 찾을 수 없습니다.")
        return json.loads(json_str)
    except Exception as e:
        logger.error(f"❌ JSON 파싱 오류: {e}, 원본 응답: {response_text}")
        raise ValueError(f"JSON 파싱 오류: {e}")
