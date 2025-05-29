# backend/utils/helpers.py

# 색상 그룹 매핑 (약학정보원 기준)
COLOR_GROUPS = {
    "하양": ["하양"],
    "노랑": ["노랑계열", "초록계열"],
    "주황": ["노랑계열"],
    "분홍": ["노랑계열"],
    "빨강": ["노랑계열"],
    "갈색": ["노랑계열"],
    "베이지": ["노랑계열"],
    "연두": ["초록계열", "노랑계열"],
    "초록": ["초록계열"],
    "청록": ["초록계열", "파랑계열"],  # ✅ 두 그룹에 포함
    "하늘": ["파랑계열"],
    "파랑": ["파랑계열"],
    "남색": ["파랑계열"],
    "자주": ["자주계열"],
    "보라": ["자주계열"],
    "회색": ["회색"],
    "검정": ["검정"],
    "투명": ["투명"]
}


# 모양 그룹 매핑 (약학정보원 기준)
SHAPE_GROUPS = {
    "원형": "원형",
    "타원형": "타원/장방형",
    "장방형": "타원/장방형",
    "반원형": "반원형",
    "삼각형": "삼각형",
    "사각형": "사각형",
    "마름모형": "마름모형",
    "오각형": "다각형",
    "육각형": "다각형",
    "팔각형": "다각형",
    "기타": "기타"
}

def normalize_color(color: str) -> str:
    """
    색상 문자열을 좌우 공백 제거 후 반환.
    """
    if not color:
        return ""
    return color.strip()

def get_color_group(color: str) -> str:
    """
    주어진 색상에 해당하는 그룹을 반환.
    해당 색상이 매핑에 없으면 "기타"를 반환.
    """
    return COLOR_GROUPS.get(color, ["기타"])

def normalize_shape(shape: str) -> str:
    """
    모양 문자열을 좌우 공백 제거 후 반환.
    """
    if not shape:
        return ""
    return shape.strip()

def get_shape_group(shape: str) -> str:
    """
    주어진 모양에 해당하는 그룹을 반환.
    해당 모양이 매핑에 없으면 "기타"를 반환.
    """
    return SHAPE_GROUPS.get(shape, "기타")

def parse_color_classes(value) -> list:
    """
    색상 정보가 문자열이면 쉼표로 분리하고, 리스트라면 각 요소에 대해 strip 처리를 수행.
    """
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    elif isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str)]
    return []

def parse_mark_code(value) -> list:
    """
    마크 코드가 문자열이면 쉼표로 분리하고, 리스트라면 각 요소에 대해 strip 처리를 수행.
    """
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    elif isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str)]
    return []
