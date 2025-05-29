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
        raw_results = response["hits"]["hits"]

        if not raw_results:
            logger.info("검색 결과가 없습니다.")
            return []

        # 점수 기반 필터링 적용
        filtered_results = filter_results_by_score(results=raw_results, min_results=1, max_results=top_k)

        logger.info(f"원본 결과 수: {len(raw_results)}, 필터링 후 결과 수: {len(filtered_results)}")

        return filtered_results

    except json.JSONDecodeError:
        logger.error("❌ JSON decoding failed: Invalid JSON format.", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"❌ Pill search failed: {e}", exc_info=True)
        return []


def filter_results_by_score(results: List[Dict[str, Any]],
                            min_results: int = 1,
                            max_results: int = 5,
                            score_threshold_ratio: float = 0.5) -> List[Dict[str, Any]]:
    """
    점수 분포를 분석하여 의미 있는 결과만 필터링

    Args:
        results: 검색 결과 리스트
        min_results: 최소 반환할 결과 수
        max_results: 최대 반환할 결과 수
        score_threshold_ratio: 1등 대비 점수 비율 임계값

    Returns:
        필터링된 결과 리스트
    """
    if not results:
        return []

    # 점수 추출 및 정렬 (이미 정렬되어 있지만 확실히)
    scores = [hit["_score"] for hit in results]
    logger.info(f"검색 결과 점수들: {scores}")

    if len(results) <= min_results:
        logger.info(f"결과가 {min_results}개 이하이므로 모든 결과 반환")
        return results

    # 1등 점수
    top_score = scores[0]

    # 점수 차이 분석
    score_gaps = []
    for i in range(len(scores) - 1):
        gap = scores[i] - scores[i + 1]
        gap_ratio = gap / top_score if top_score > 0 else 0
        score_gaps.append({
            'position': i + 1,
            'gap': gap,
            'gap_ratio': gap_ratio,
            'current_score': scores[i],
            'next_score': scores[i + 1]
        })

    logger.info(f"점수 차이 분석: {score_gaps}")

    # 필터링 로직
    cutoff_position = len(results)  # 기본적으로 모든 결과 포함

    # 방법 1: 큰 점수 차이가 있는 지점에서 자르기
    for gap_info in score_gaps:
        if gap_info['gap_ratio'] > 0.15:  # 1등 대비 15% 이상 차이나는 지점
            cutoff_position = gap_info['position']
            logger.info(f"큰 점수 차이 발견: {gap_info['position']}등에서 {gap_info['gap']:.2f}점 차이")
            break

    # 방법 2: 1등 대비 임계값 이하인 결과들 제거
    threshold_score = top_score * score_threshold_ratio
    threshold_cutoff = len(results)

    for i, score in enumerate(scores):
        if score < threshold_score:
            threshold_cutoff = i
            logger.info(f"임계값({threshold_score:.2f}) 이하 점수 발견: {i + 1}등부터 제외")
            break

    # 두 방법 중 더 보수적인 것 선택 (더 많은 결과 포함)
    final_cutoff = max(min(cutoff_position, threshold_cutoff), min_results)
    final_cutoff = min(final_cutoff, max_results)

    logger.info(f"최종 cutoff 위치: {final_cutoff}")

    # 결과 필터링
    filtered_results = results[:final_cutoff]

    # 필터링 결과 로깅
    filtered_scores = [hit["_score"] for hit in filtered_results]
    logger.info(f"필터링된 결과 점수들: {filtered_scores}")

    return filtered_results


def analyze_score_distribution(scores: List[float]) -> Dict[str, Any]:
    """
    점수 분포 분석을 위한 헬퍼 함수
    """
    if not scores:
        return {}

    import statistics

    analysis = {
        'count': len(scores),
        'max': max(scores),
        'min': min(scores),
        'range': max(scores) - min(scores),
        'mean': statistics.mean(scores),
        'median': statistics.median(scores)
    }

    if len(scores) > 1:
        analysis['std_dev'] = statistics.stdev(scores)
        analysis['coefficient_of_variation'] = analysis['std_dev'] / analysis['mean'] if analysis['mean'] > 0 else 0

    return analysis

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
    - 일반 쿼리: 모양, 색상, 인쇄문자 모두 검색
    - 투명 예외 쿼리: 투명 색상 의약품은 shape_group과 imprint가 일치하면 검색에 포함
    """
    should_clauses = []
    filter_clauses = []
    shape_group_filter = None

    # 1. 모양 그룹 필터
    if "shape_group" in norm:
        shape_group_filter = {"term": {"shape_group": norm["shape_group"]}}
        filter_clauses.append(shape_group_filter)
    
    # 2. 색상 그룹 필터
    if "primary_color_group" in norm:
        if "secondary_color_group" in norm:
            filter_clauses.append({
                "bool": {
                    "should": [
                        {"terms": {"color_group": norm["primary_color_group"]}},
                        {"terms": {"color_group": norm["secondary_color_group"]}}
                    ],
                    "minimum_should_match": 1
                }
            })
        else:
            filter_clauses.append({
                "terms": {"color_group": norm["primary_color_group"]}
            })

    # 3. 인쇄문자 및 마크 코드 관련 쿼리
    imprint = norm.get("imprint", "")
    is_mark = norm.get("is_mark", False)
    
    if imprint:
        # 정확한 일치: keyword 필드를 사용
        should_clauses.append({
            "term": {
                "print_front.keyword": {"value": imprint, "boost": 10.0}
            }
        })
        should_clauses.append({
            "term": {
                "print_back.keyword": {"value": imprint, "boost": 10.0}
            }
        })
        # 퍼지 매칭: fuzzy 옵션 활용
        should_clauses.append({
            "match": {
                "print_front": {"query": imprint, "boost": 5.0, "fuzziness": "AUTO"}
            }
        })
        should_clauses.append({
            "match": {
                "print_back": {"query": imprint, "boost": 5.0, "fuzziness": "AUTO"}
            }
        })
        # 마크 코드 검색
        if is_mark:
            should_clauses.append({
                "match": {
                    "mark_code_front_anal": {"query": imprint, "boost": 8.0}
                }
            })
            should_clauses.append({
                "match": {
                    "mark_code_back_anal": {"query": imprint, "boost": 8.0}
                }
            })
        else:
            should_clauses.append({
                "match": {
                    "mark_code_front_anal": {"query": imprint, "boost": 4.0}
                }
            })
            should_clauses.append({
                "match": {
                    "mark_code_back_anal": {"query": imprint, "boost": 4.0}
                }
            })
        # 유사 문자 변형에 따른 검색
        for variation in norm.get("imprint_variations", []):
            should_clauses.append({
                "term": {
                    "print_front.keyword": {"value": variation, "boost": 8.0 if is_mark else 5.0}
                }
            })
            should_clauses.append({
                "term": {
                    "print_back.keyword": {"value": variation, "boost": 8.0 if is_mark else 5.0}
                }
            })
            should_clauses.append({
                "match": {
                    "mark_code_front_anal": {"query": variation, "boost": 6.0 if is_mark else 3.0}
                }
            })
            should_clauses.append({
                "match": {
                    "mark_code_back_anal": {"query": variation, "boost": 6.0 if is_mark else 3.0}
                }
            })

    # 4. 최종 쿼리 구성: 두 개의 독립적인 쿼리를 OR로 결합
    main_query = {
        "bool": {
            "filter": filter_clauses,
            "should": should_clauses,
            "minimum_should_match": 1 if should_clauses else 0
        }
    }
    
    # 투명 색상 쿼리: shape_group과 imprint가 일치하면 결과에 포함
    transparent_query = None
    if imprint and shape_group_filter:  # imprint와 shape_group이 모두 있을 때만 투명 쿼리 추가
        transparent_should = []
        
        # 동일한 imprint 검색 조건
        transparent_should.append({
            "term": {"print_front.keyword": {"value": imprint, "boost": 10.0}}
        })
        transparent_should.append({
            "term": {"print_back.keyword": {"value": imprint, "boost": 10.0}}
        })
        transparent_should.append({
            "match": {"print_front": {"query": imprint, "boost": 5.0, "fuzziness": "AUTO"}}
        })
        transparent_should.append({
            "match": {"print_back": {"query": imprint, "boost": 5.0, "fuzziness": "AUTO"}}
        })
        
        # 유사 문자 변형도 포함
        for variation in norm.get("imprint_variations", []):
            transparent_should.append({
                "term": {"print_front.keyword": {"value": variation, "boost": 5.0}}
            })
            transparent_should.append({
                "term": {"print_back.keyword": {"value": variation, "boost": 5.0}}
            })
        
        transparent_query = {
            "bool": {
                "must": [
                    {"term": {"color_group": "투명"}},  # 색상이 투명인 항목
                    shape_group_filter  # shape_group 필터 추가
                ],
                "should": transparent_should,
                "minimum_should_match": 1  # 최소 하나의 imprint 조건 일치
            }
        }
    
    # 두 쿼리를 OR로 결합
    query_body = {
        "size": top_k,
        "query": {
            "bool": {
                "should": [
                    main_query,  # 일반 검색 쿼리
                    transparent_query if transparent_query else {"match_none": {}}  # 투명 예외 쿼리 (없으면 match_none)
                ],
                "minimum_should_match": 1
            }
        },
        "sort": [{"_score": {"order": "desc"}}]
    }
    
    return query_body
