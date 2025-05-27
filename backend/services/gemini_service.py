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
    try:
        with Image.open(image_path) as img:
            img_byte_arr = io.BytesIO()
            img_format = img.format if img.format else "JPEG"
            img.save(img_byte_arr, format=img_format)
            img_bytes = img_byte_arr.getvalue()
        
        # 프롬프트: 반드시 필요한 3가지 필드만 반환하도록 요청합니다.
        prompt = (
            "다음은 약품 이미지 분석 요청입니다.\n\n"
            "당신(Gemini)은 이미지에서 약품의 식별 특성을 추출해야 하며, **아래 3가지 항목만 JSON 형식으로 반환**해야 합니다:\n\n"
            "1. \"drug_shape\" – 약품의 모양. 다음 중 정확히 일치하는 단어 하나를 사용하세요: "
            "원형, 타원형, 장방형, 반원형, 삼각형, 사각형, 마름모형, 오각형, 육각형, 팔각형, 기타\n\n"
            "2. \"color_classes\" – 약품의 색상.\n"
            "- 단일 색상인 경우 문자열 (예: \"분홍\")\n"
            "- 두 가지 색상이 조합된 경우 리스트 (예: [\"하양\", \"분홍\"])\n"
            "- 색상은 반드시 아래 목록에서 '정확히 일치하는 단어'만 사용하십시오: "
            "하양, 노랑, 주황, 분홍, 빨강, 갈색, 연두, 초록, 청록, 파랑, 남색, 자주, 보라, 회색, 검정, 투명\n\n"
            "- 연질 캡슐인 것 같다면, \"투명\"을 포함하세요.\n"
            "3. \"imprint\": 약품에 인쇄된 문자(A-Z, a-z), 숫자(0-9), 그리고 + 등의 일반 특수기호를 정확히 추출하세요.\n"
            "- 영어 대소문자를 구분해야 합니다.\n"
            "- 중앙에 분할선이 있는 경우, 반드시 '|' 기호 하나로만 구분하십시오.\n"
            "- 줄바꿈(\\n), 탭(\\t), 역슬래시(\\), 따옴표(\") 등은 절대 포함하지 마세요.\n\n"
            "- **매우 중요**: 줄바꿈(\\n), 탭(\\t), 역슬래시(\\), 따옴표(\")와 같은 이스케이프 문자는 절대 포함하지 마세요.\n\n"
            "※ 이미지에 여러 개의 약품이 감지된다면, 각 약품에 대해 위 정보를 포함한 JSON 객체를 배열 형태로 반환하세요.\n\n"
            "예시 반환:\n"
            "[\n"
            "  {\"drug_shape\": \"원형\", \"color_classes\": \"하양\", \"imprint\": \"A+\"},\n"
            "  {\"drug_shape\": \"장방형\", \"color_classes\": [\"하양\", \"분홍\"], \"imprint\": \"Q|200\"}\n"
            "]"
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
