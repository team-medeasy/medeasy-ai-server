import os
import logging
from elasticsearch import AsyncElasticsearch
from dotenv import load_dotenv

from backend.utils.helpers import normalize_color, get_color_group, normalize_shape, get_shape_group

logger = logging.getLogger(__name__)
load_dotenv()

# 환경변수에서 Elasticsearch 연결 정보 읽기
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "elasticsearch")
ELASTICSEARCH_PORT = os.getenv("ELASTICSEARCH_PORT", "9200")
ELASTICSEARCH_URL = f"http://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}"
INDEX_NAME = os.getenv("ELASTICSEARCH_INDEX", "pills_v5")

ELASTIC_USER = os.getenv("ELASTIC_USER", "elastic")
ELASTIC_PASSWORD = os.getenv("ELASTIC_PASSWORD", "your_password")

# AsyncElasticsearch 클라이언트 생성
es = AsyncElasticsearch(
    [ELASTICSEARCH_URL],
    basic_auth=(ELASTIC_USER, ELASTIC_PASSWORD)
)
logger.warning(f"ES 연결 확인: {ELASTICSEARCH_URL} / USER: {ELASTIC_USER}")



# # Elasticsearch 인덱스 매핑 (dense_vector 필드 등 포함)
# INDEX_MAPPING = {
#     "settings": {
#         "analysis": {
#             "char_filter": {
#                 "remove_pipe": {
#                     "type": "pattern_replace",
#                     "pattern": "\\|",
#                     "replacement": ""
#                 }
#             },
#             "tokenizer": {
#                 "korean_tokenizer": {
#                     "type": "nori_tokenizer"
#                 },
#                 "english_ngram_tokenizer": {
#                     "type": "ngram",
#                     "min_gram": 2,
#                     "max_gram": 3,
#                     "token_chars": ["letter", "digit"]
#                 }
#             },
#             "analyzer": {
#                 "custom_korean_english": {
#                     "tokenizer": "standard",
#                     "filter": ["lowercase"],
#                     "char_filter": ["remove_pipe"]
#                 },
#                 "korean_only": {
#                     "tokenizer": "korean_tokenizer",
#                     "char_filter": ["remove_pipe"]
#                 },
#                 "english_ngram_analyzer": {
#                     "tokenizer": "english_ngram_tokenizer",
#                     "filter": ["lowercase"]
#                 }
#             }
#         }
#     },
#     "mappings": {
#         "properties": {
#             "embedding": {
#                 "type": "dense_vector",
#                 "dims": 384,
#                 "index": True,
#                 "similarity": "cosine"
#             },
#             "item_seq": {"type": "keyword"},
#             "print_front": {
#                 "type": "text",
#                 "analyzer": "custom_korean_english",
#                 "fields": {
#                     "keyword": {"type": "keyword"}
#                 }
#             },
#             "print_back": {
#                 "type": "text",
#                 "analyzer": "custom_korean_english",
#                 "fields": {
#                     "keyword": {"type": "keyword"}
#                 }
#             },
#             "print_front_normalized": {
#                 "type": "text",
#                 "analyzer": "english_ngram_analyzer"
#             },
#             "print_back_normalized": {
#                 "type": "text",
#                 "analyzer": "english_ngram_analyzer"
#             },
#             "drug_shape": {"type": "keyword"},
#             "color_classes": {"type": "keyword"},
#             "shape_group": {"type": "keyword"},
#             "color_group": {"type": "keyword"},
#             "mark_code_front_anal": {
#                 "type": "text",
#                 "analyzer": "custom_korean_english"
#             },
#             "mark_code_back_anal": {
#                 "type": "text",
#                 "analyzer": "custom_korean_english"
#             }
#         }
#     }
# }

# def process_pill_data(pill_data: dict) -> dict:
#     """
#     Elasticsearch에 저장하기 위해 pill_data를 전처리합니다.
#       - color_classes를 단일 문자열로 전환하고, color_group 필드 추가
#       - drug_shape 정규화 후, shape_group 추가
#     """
#     data = pill_data.copy()
#     # _id 필드 제거
#     data.pop("_id", None)
    
#     color = ""
#     if "color_classes" in data and data["color_classes"]:
#         if isinstance(data["color_classes"], list):
#             color = data["color_classes"][0]
#         else:
#             color = data["color_classes"]
#         color = normalize_color(color)
#         data["color_classes"] = color
#         data["color_group"] = get_color_group(color)
    
#     # 모양 처리
#     if "drug_shape" in data and data["drug_shape"]:
#         shape = normalize_shape(data["drug_shape"])
#         data["drug_shape"] = shape
#         data["shape_group"] = get_shape_group(shape)
    
#     return data

# async def setup_elasticsearch() -> bool:
#     """
#     Elasticsearch 연결을 확인하고, 인덱스가 존재하지 않을 경우 생성.
#     연결 및 인덱스 설정 성공 시 True, 실패 시 False 반환.
#     """
#     try:
#         # 클러스터 상태 확인
#         health = await es.cluster.health()
#         logger.info(f"Elasticsearch cluster health: {health['status']}")

#         # 인덱스 존재 여부 확인
#         index_exists = await es.indices.exists(index=INDEX_NAME)
#         if not index_exists:
#             logger.info(f"Creating index '{INDEX_NAME}'...")
#             await es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
#             logger.info(f"Index '{INDEX_NAME}' created successfully.")
#         else:
#             logger.info(f"Index '{INDEX_NAME}' already exists.")
#         return True
#     except Exception as e:
#         logger.error(f"Elasticsearch setup failed: {e}")
#         return False

async def check_elasticsearch_connection() -> bool:
    try:
        health = await es.cluster.health()
        logger.info(f"Elasticsearch cluster health: {health['status']}")
        return True
    except Exception as e:
        logger.error(f"Elasticsearch connection check failed: {e}", exc_info=True)
        return False
    
async def close_elasticsearch() -> None:
    """
    Elasticsearch 연결 종료.
    """
    try:
        await es.close()
        logger.info("Elasticsearch connection closed.")
    except Exception as e:
        logger.error(f"Elasticsearch closing error: {e}")