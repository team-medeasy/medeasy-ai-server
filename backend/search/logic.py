# backend/search/logic.py
import json
from typing import Dict, Any, List
import logging

from fastapi import HTTPException

from backend.utils.helpers import normalize_color, get_color_group, normalize_shape, get_shape_group
from backend.search.transform import generate_character_variations

logger = logging.getLogger(__name__)

from backend.db.elastic import es, INDEX_NAME

async def search_pills(features: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
    try:
        # features가 문자열(str)이라면 JSON으로 변환
        if isinstance(features, str):
            features = json.loads(features)  # JSON 문자열을 딕셔너리로 변환

        norm_features = preprocess_features(features)
        query_body = build_es_query(norm_features, top_k)
        logger.warning(f"QUERY BODY:\n{json.dumps(query_body, indent=2, ensure_ascii=False)}")
        response = await es.search(index=INDEX_NAME, body=query_body)
        return response["hits"]["hits"]
    except json.JSONDecodeError:
        logger.error("❌ JSON decoding failed: Invalid JSON format.", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"❌ Pill search failed: {e}", exc_info=True)
        return []

async def search_medicine_by_item_seq(item_seq: str)-> Dict[str, Any]:
    try:
        query = {
                    "term": {
                        "item_seq": {
                            "value": item_seq
                        }
                    }
                }

        result = await es.search(
            index="medicine_data",
            body={
                "query": query,
                "size": 1  # 단일 문서만 반환
            }
        )
        hits = result.get("hits", {}).get("hits", [])
        doc = hits[0]["_source"]

        return doc
    except Exception as e:
        logger.error(f"의약품 검색 중 오류 발생: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="의약품 검색 중 오류가 발생했습니다."
        )


def preprocess_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    사용자로부터 받은 검색 파라미터를 전처리합니다.
      - drug_shape: normalize_shape와 get_shape_group를 이용해 정규화
      - color_classes: 단일 문자열이면 리스트로 변환하고, 주색상/보조색상 구분 후 그룹화
      - imprint: 좌우 공백 제거, '마크' 포함 여부 체크, 유사 문자 변형 생성
    """
    norm = {}

    # 모양 정규화
    if "drug_shape" in features and features["drug_shape"]:
        shape = normalize_shape(features["drug_shape"])
        norm["drug_shape"] = shape
        norm["shape_group"] = get_shape_group(shape)

    # 색상 정규화 (단일 문자열이면 리스트로)
    if "color_classes" in features and features["color_classes"]:
        color_val = features["color_classes"]
        if isinstance(color_val, str):
            color_list = [color_val]
        else:
            color_list = color_val
        if color_list:
            primary = normalize_color(color_list[0])
            norm["primary_color"] = primary
            norm["primary_color_group"] = get_color_group(primary)
        if len(color_list) > 1:
            secondary = normalize_color(color_list[1])
            norm["secondary_color"] = secondary
            norm["secondary_color_group"] = get_color_group(secondary)

    # 인쇄문자(imprint) 처리
    imprint = features.get("imprint", "").strip()
    norm["imprint"] = imprint
    norm["is_mark"] = "마크" in imprint
    norm["imprint_variations"] = generate_character_variations(imprint) if imprint else []

    return norm

def build_es_query(norm: Dict[str, Any], top_k: int) -> Dict[str, Any]:
    """
    Elasticsearch 쿼리문을 구성합니다.
    - 필터(모양/색상 그룹)와
    - should 절(인쇄문자, 마크 코드, 유사 문자 변형)을 포함하여 쿼리를 만듭니다.
    - 투명 색상 의약품은 색상 필터와 관계없이 shape_group과 imprint가 일치하면 결과에 포함시킵니다.
    """
    should_clauses = []
    filter_clauses = []

    # 1. 모양 그룹 필터
    shape_group_filter = None
    if "shape_group" in norm:
        shape_group_filter = {"term": {"shape_group": norm["shape_group"]}}
        filter_clauses.append(shape_group_filter)
    
    # 2. 색상 그룹 필터
    color_filter = None
    if "primary_color_group" in norm:
        if "secondary_color_group" in norm:
            color_filter = {
                "bool": {
                    "should": [
                        {"term": {"color_group": norm["primary_color_group"]}},
                        {"term": {"color_group": norm["secondary_color_group"]}}
                    ],
                    "minimum_should_match": 1
                }
            }
        else:
            color_filter = {
                "term": {"color_group": norm["primary_color_group"]}
            }
        filter_clauses.append(color_filter)

    # 3. 인쇄문자 및 마크 코드 관련 쿼리
    imprint = norm.get("imprint", "")
    is_mark = norm.get("is_mark", False)
    imprint_clauses = []  # imprint 검색 조건 저장
    
    if imprint:
        # 정확한 일치: keyword 필드를 사용
        imprint_clauses.append({
            "term": {
                "print_front.keyword": {"value": imprint, "boost": 10.0}
            }
        })
        imprint_clauses.append({
            "term": {
                "print_back.keyword": {"value": imprint, "boost": 10.0}
            }
        })
        # 퍼지 매칭: fuzzy 옵션 활용
        imprint_clauses.append({
            "match": {
                "print_front": {"query": imprint, "boost": 5.0, "fuzziness": "AUTO"}
            }
        })
        imprint_clauses.append({
            "match": {
                "print_back": {"query": imprint, "boost": 5.0, "fuzziness": "AUTO"}
            }
        })
        # 마크 코드 검색
        if is_mark:
            imprint_clauses.append({
                "match": {
                    "mark_code_front_anal": {"query": imprint, "boost": 8.0}
                }
            })
            imprint_clauses.append({
                "match": {
                    "mark_code_back_anal": {"query": imprint, "boost": 8.0}
                }
            })
        else:
            imprint_clauses.append({
                "match": {
                    "mark_code_front_anal": {"query": imprint, "boost": 4.0}
                }
            })
            imprint_clauses.append({
                "match": {
                    "mark_code_back_anal": {"query": imprint, "boost": 4.0}
                }
            })
        # 유사 문자 변형에 따른 검색
        for variation in norm.get("imprint_variations", []):
            imprint_clauses.append({
                "term": {
                    "print_front.keyword": {"value": variation, "boost": 8.0 if is_mark else 5.0}
                }
            })
            imprint_clauses.append({
                "term": {
                    "print_back.keyword": {"value": variation, "boost": 8.0 if is_mark else 5.0}
                }
            })
            imprint_clauses.append({
                "match": {
                    "mark_code_front_anal": {"query": variation, "boost": 6.0 if is_mark else 3.0}
                }
            })
            imprint_clauses.append({
                "match": {
                    "mark_code_back_anal": {"query": variation, "boost": 6.0 if is_mark else 3.0}
                }
            })
        
        # should_clauses에 imprint 검색 조건 추가
        should_clauses.extend(imprint_clauses)

    # 4. 투명 색상 약품을 위한 추가 쿼리 (색상 필터 무시)
    transparent_query = None
    if imprint_clauses:  # imprint가 있으면 투명 색상에 대한 예외 처리 추가
        transparent_must = [{"term": {"color_group": "투명"}}]
        
        # shape_group 필터가 있다면 포함
        if shape_group_filter:
            transparent_must.append(shape_group_filter)
            
        transparent_query = {
            "bool": {
                "must": transparent_must,
                "should": imprint_clauses,
                "minimum_should_match": 1  # 적어도 하나의 imprint 조건 일치 필요
            }
        }

    # 최종 쿼리 구성
    if transparent_query:
        # 투명 색상 예외 처리가 있는 경우
        query_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "should": [
                        # 일반 검색 조건
                        {
                            "bool": {
                                "filter": filter_clauses,
                                "should": should_clauses,
                                "minimum_should_match": 1 if should_clauses else 0
                            }
                        },
                        # 투명 색상 예외 처리
                        transparent_query
                    ],
                    "minimum_should_match": 1
                }
            },
            "sort": [{"_score": {"order": "desc"}}]
        }
    else:
        # 기존 쿼리 그대로 사용
        query_body = {
            "size": top_k,
            "query": {
                "bool": {
                    "filter": filter_clauses,
                    "should": should_clauses,
                    "minimum_should_match": 1 if should_clauses else 0
                }
            },
            "sort": [{"_score": {"order": "desc"}}]
        }
    
    return query_body
